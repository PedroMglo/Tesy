"""Repeat the fixed-exterior CPU calculation, using each process's own clocks and gaps."""

import argparse
import json
from collections import Counter
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = run_path(str(HERE.parent / "evaluate.py"))
T, PREV = Q["T"], Q["B"]["PREV"]
CLIENT = run_path(str(HERE.parents[1] / "client_cut.py"))
check, pinned = Q["check"], Q["pinned"]
METHOD = "aa886859cf8fa55821e7a6438f3445a59457bc5305243261e389a79a9018274f"


def assess(root, receipt, rows, tiers, banks, offered):
    host = T["NATIVE"]["host_trace"](rows)
    check(len(host["calls"]) == 48, "two prefill and 46 decode calls")
    cut = CLIENT["inspect"](root, receipt, host["calls"])
    check(cut["sample_number"] == 45 and cut["sample_call"] == 46, "first final")
    log = root / "raw" / receipt["native_ids"]["raw_stderr_file"]
    check(
        Q["digest"](log) == receipt["native_ids"]["stderr_sha256"]
        and T["mapping"](log.read_bytes(), rows)[0] == tiers,
        "tier map in this producer",
    )
    spans = T["intervals"](rows, host["callback_spans"])
    final = host["calls"][45]["return_ns"] + cut["last_relevant_return_to_first_final_ns"]
    prices = T["buckets"](spans, tiers, host["calls"], final)
    payload = json.loads((root / "raw/T2-result.json").read_bytes())
    first = int(
        (
            Decimal(str(payload["stream_metrics"]["first_final_content_chunk_s"])) * 10**9
        ).to_integral_value(rounding=ROUND_FLOOR)
    )
    decode = int(
        (Decimal(str(payload["timings"]["predicted_ms"])) * 10**6).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    check(
        payload["timings"]["predicted_n"] == 47 and payload["timings"]["prompt_n"] == 153,
        "work denominators",
    )
    published = receipt["rows"][1]
    check(
        published["functional"] == "PASS"
        and published["completion"] == "stop"
        and published["completion_n"] == published["predicted_n"] == 47
        and published["prompt_n"] == 153
        and published["cache_n"] == 2044
        and abs(float(first) / 10**9 - published["first_final_s"]) < 2e-9
        and abs(float(decode) / 10**9 - published["decode_s"]) < 2e-9,
        "terminal clocks and denominators differ from sealed grade",
    )
    sc = T["scenario"](prices, first, decode)["scenarios"]["CPU"]
    budget = 10**10 - sc["remaining_floor_ns"]["first"]
    route, _, cpu = Q["read_current"](rows, tiers)
    cells, index = PREV["trace_cuts"](rows)
    windows, modes = {}, Counter()
    last = 0
    for site in sorted(set(cpu.values())):
        condition, gap = PREV["horizon"](cells, index, site)
        modes[condition] += 1
        if condition not in ("drained", "layer0") or gap is None:
            return {"status": "INCONCLUSIVE_WINDOWS", "reason": condition, "site": site}
        start = cells[site[:3]][0][0].ns
        check(start - gap >= last, "overlapping first-use windows")
        last = start
        windows[site] = gap
    estimates, _ = Q["project"](cpu, windows, banks, offered, budget)
    return {
        "status": "TRACE_DERIVED_OBSERVED_CLOCK",
        "route": route,
        "T2_result_sha256": Q["digest"](root / "raw/T2-result.json"),
        "T2_client_sha256": Q["digest"](root / "raw/T2-request.jsonl"),
        "first_final_ns": first,
        "decode_ns": decode,
        "client_cut": cut,
        "cpu_remaps": sc,
        "CPU_first_final_budget_ns": budget,
        "CPU_decode_budget_ns": (47 * 10**9 + 5) // 6 - sc["remaining_floor_ns"]["decode"],
        "strict_cpu_jobs": len(cpu),
        "horizons": modes,
        "gap_ns": sum(windows.values()),
        "arms": estimates,
    }


def compare(a):
    check(Q["digest"](HERE / "protocol.md") == METHOD, "protocol")
    selection, current, tiers, gates = Q["read_new"](a.session, a.session_sha256)
    banks = {k: set(map(tuple, v["ordered_keys"])) for k, v in selection["banks"].items()}
    offered = set(map(tuple, selection["offered_keys"]))
    historical = Q["CHAIN"]["chain"](a.p97, Q["P97"])
    _, _, old_receipt, _ = historical
    old, header = T["PFJ"]["read_journal"](a.p97 / "ON/raw/events.pfj")
    check(
        header["journal_sha256"]
        == "05e32c2af753026e471fa61c9dcb43867ca6b9a3001045a2138bc96c422928dc",
        "historical packed journal",
    )
    family = pinned(a.session / "family.json", a.session_sha256)
    link = family["arms"]["ON"]
    on = a.session / "ON"
    meta = pinned(on / "arm.json", link["sha256"])
    receipt = pinned(on / "receipt.json", meta["receipt_sha256"])
    own = assess(on, receipt, current, tiers, banks, offered)
    prior = assess(a.p97 / "ON", old_receipt, old, tiers, banks, offered)
    check(prior["CPU_first_final_budget_ns"] == 90641339, "replicated prior budget")
    consistent = own["status"] == prior["status"] and own.get("route") == prior["route"]
    old_cpu = Q["read_current"](old, tiers)[2]
    current_cpu = Q["read_current"](current, tiers)[2]
    matching = {
        "initial_slots": Q["delta"](Q["bindings"](old), Q["bindings"](current)),
        "strict_CPU_sites": Q["delta"](old_cpu, current_cpu),
    }
    consistent = consistent and all(
        all(v[k] == 0 for k in ("reference_only", "new_only", "different"))
        for v in matching.values()
    )
    verdicts = {}
    if consistent:
        for price in own["arms"]:
            verdicts[price] = {
                arm: {
                    k: v["arms"][price][arm]["margin_ns"] >= 0
                    for k, v in (("P97", prior), ("new", own))
                }
                for arm in banks.keys() | {"empty", "retrospective"}
            }
    return {
        "status": "PAIRED_SCENARIO_SIGNS" if consistent else "INCONCLUSIVE_COMPARISON",
        "protocol_sha256": METHOD,
        "inputs": gates,
        "historical_family_sha256": Q["P97"],
        "same_shadow_selection_in_both": True,
        "correspondence": matching,
        "headroom": verdicts,
        "P97": prior,
        "new": own,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("session", "p97", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--session-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = compare(a)
    except Exception as exc:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": str(exc)}) + "\n")
        raise
    with (a.new_output_dir / "receipt.json").open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
