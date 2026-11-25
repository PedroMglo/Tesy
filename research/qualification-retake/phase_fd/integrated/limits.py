"""Price the verified nominal PFJ1 window, including a relaxed first-decode handoff."""

import argparse
import collections
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pfj_limits_auditor", HERE / "analyse.py")
pfj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pfj)
check = pfj.check


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path, digest):
    check(sha(path) == digest, "input digest: " + path.name)
    return json.loads(path.read_bytes())


def scenario(prefill_ns, remove_ns, budget_ns):
    check(0 <= remove_ns <= prefill_ns, "inconsistent observed clocks")
    remaining = prefill_ns - remove_ns
    return {
        "remaining_ns": remaining,
        "budget_ns": budget_ns,
        "excess_ns": remaining - budget_ns,
        "decision": "NO_GO_FIXED_REMAINDER" if remaining > budget_ns else "HEADROOM_ONLY",
    }


def service_window(rows, calls):
    initial, current, weights = {}, {}, {}
    requests = collections.defaultdict(list)
    callback_spans = []
    begin = None
    for row in rows:
        if row.kind == 1 and row.call == 3:
            break
        slot = (row.layer, row.slot)
        if row.kind == 5:
            initial[slot] = current[slot] = (row.expert, row.a)
        elif row.kind == 8:
            weights[(row.layer, row.component)] = row.b
        elif row.kind == 11:
            current[slot] = (row.expert, 1)
        elif row.kind == 17:
            current[slot] = (row.expert, 2)
        elif row.kind == 10:
            requests[row.layer].append(row.expert)
        elif row.kind == 9:
            check(begin is None, "nested callbacks")
            begin = row.ns
        elif row.kind == 23:
            check(begin is not None, "callback end")
            callback_spans.append((begin, row.ns))
            begin = None
    else:
        raise ValueError("first decode missing")
    check(begin is None and len(initial) == len(current) == 1440, "incomplete first-decode cut")
    counts = collections.Counter()
    for layer in range(36):
        present = {initial[(layer, s)][0] for s in range(40) if initial[(layer, s)][1]}
        restored = [current[(layer, s)][0] for s in range(40) if current[(layer, s)][1] == 2]
        size = sum(weights[(layer, k)] for k in range(3))
        sequence = requests[layer]
        relaxed = pfj.belady(sequence, present)
        handoff = pfj.belady(sequence + restored, present)
        counts["load_floor"] += relaxed
        counts["payload_floor"] += relaxed * size
        counts["load_floor_with_handoff"] += handoff
        counts["payload_floor_with_handoff"] += handoff * size
        counts["first_decode_resident"] += len(restored)
    counts["first_decode_loading"] = sum(state == 1 for _, state in current.values())
    gap = calls[2]["start_ns"] - calls[1]["end_ns"]
    call_five = calls[0]["end_ns"] - calls[0]["start_ns"]
    check(min(gap, call_five) >= 0, "external clock ordering")
    return {
        "relaxed": dict(counts),
        "callbacks_union_ns": pfj.union_ns(callback_spans),
        "calls": [
            {
                "tokens": c["tokens"],
                "native_duration_ns": c["end_ns"] - c["start_ns"],
                "blocking_publications": c["blocking_publications"],
                "origin_loads": c["origin_loads"],
                "origin_returned_bytes": c["origin_returned_bytes"],
            }
            for c in calls[:2]
        ],
        "return_148_to_enter_decode_ns": gap,
        "call_five_ns": call_five,
        "return_five_to_enter_148_ns": calls[1]["start_ns"] - calls[0]["end_ns"],
    }


def joint_clock(rows, calls, raw, public):
    check(
        abs(public["first_final_s"] - raw["stream_metrics"]["first_final_content_chunk_s"]) < 1e-6
        and abs(public["valid_wall_s"] - raw["request_wall_s"]) < 0.01,
        "client/receipt clocks",
    )
    start = math.floor(raw["request_started_monotonic"] * 1e9)
    end = math.ceil(raw["request_ended_monotonic"] * 1e9)
    first = math.ceil(start + raw["stream_metrics"]["first_final_content_chunk_s"] * 1e9)
    check(
        start <= calls[0]["start_ns"] < first <= end and calls[-1]["end_ns"] <= end + 10**6,
        "native/POST ordering",
    )
    spans = collections.defaultdict(list)
    begins = {}
    events = {
        9: ("remap", 1),
        23: ("remap", 0),
        19: ("barrier", 1),
        20: ("barrier", 0),
        21: ("victim", 1),
        22: ("victim", 0),
    }
    for r in rows:
        if r.kind not in events:
            continue
        key, opens = events[r.kind]
        if key == "barrier" and not r.a:
            continue
        if opens:
            check(key not in begins, "nested spans")
            begins[key] = r.ns
        else:
            spans[key].append((r.call, begins.pop(key), r.ns))
    check(not begins, "unclosed spans")
    cuts = {}
    for k, values in list(spans.items()) + [("wait", spans["barrier"] + spans["victim"])]:
        client = [
            (max(a, start - 10**6), min(b, first + 10**6))
            for _, a, b in values
            if max(a, start - 10**6) < min(b, first + 10**6)
        ]
        cuts[k] = {
            "until_first_final_ns": pfj.union_ns(client),
            "in_decode_ns": pfj.union_ns([(a, b) for call, a, b in values if call >= 3]),
        }
    to_final = max(0, first - start - 10**10 - 10**6)
    to_rate = max(0, math.floor(public["decode_s"] * 1e9) - math.ceil(47 * 10**9 / 6))
    required = {}
    for k in ("remap", "wait"):
        c = cuts[k]
        a, b = c["until_first_final_ns"], c["in_decode_ns"]
        check(a > 0 and b > 0, "missing required scope")
        required[k] = {
            "first_final_fraction": to_final / a,
            "decode_fraction": to_rate / b,
            "joint_minimum_fraction": max(to_final / a, to_rate / b),
        }
    return {
        "unions": cuts,
        "required_reduction_ns_until_final": to_final,
        "required_reduction_ns_decode": to_rate,
        "fractions": required,
    }


def execute(args):
    off = load(args.off_dir / "receipt.json", args.off_sha256)
    on = load(args.on_dir / "receipt.json", args.on_sha256)
    check(
        off["status"] == "PASS_C281_PFJ_OFF"
        and on["mode"] == "ON"
        and on["status"] == "PASS_C281_PFJ_ON"
        and off["gates"] == on["gates"],
        "physical receipts",
    )
    journal = args.on_dir / "raw/events.pfj"
    records, header = pfj.read_journal(journal)
    check(header["journal_sha256"] == on["journal_sha256"], "PFJ1 identity")
    grade = pfj.audit(records, header, args.model)
    check(
        grade["status"] == "PASS"
        and grade == load(args.on_dir / "journal-audit.json", on["journal_audit_sha256"]),
        "independent full replay",
    )
    result = service_window(records, grade["calls"])
    archive = load(args.archive_manifest, args.archive_sha256)
    raw_relative = args.on_dir.name + "/raw/T2-result.json"
    raw = load(args.on_dir / "raw/T2-result.json", archive["files"][raw_relative]["sha256"])
    result["client_clock"] = joint_clock(records, grade["calls"], raw, on["rows"][1])
    phase = grade["nominal_prefill"]
    check(
        result["relaxed"]["payload_floor"] == phase["relaxed_40slot_payload_floor"],
        "cross-calculation",
    )
    prices = on["own_ON_price"]
    costs = {}
    for label, price in prices.items():
        if not isinstance(price, dict) or "conditional_prompt_budget_ns_upper" not in price:
            continue
        budget = price["conditional_prompt_budget_ns_upper"]
        row = on["rows"][1]
        # Round the prefill floor downward; grant the candidate the entire measured interval.
        prefill_ns = math.floor(row["prefill_s"] * 10**9)
        limit = price["scenario_bytes_at_4_5GBps"]
        restored = result["relaxed"]["payload_floor_with_handoff"]
        extra = math.ceil(result["return_148_to_enter_decode_ns"] * 4.5)
        costs[label] = {
            "remove_all_remap": scenario(prefill_ns, result["callbacks_union_ns"], budget),
            "remove_call_five": scenario(prefill_ns, result["call_five_ns"], budget),
            "budget_bytes": limit,
            "unlimited_cache_margin_B": limit - phase["compulsory_payload_floor"],
            "forty_slot_margin_B": limit - phase["relaxed_40slot_payload_floor"],
            "forty_slot_handoff_margin_including_gap_B": limit + extra - restored,
        }
    check(len(costs) == 2, "both denominators")
    result.update(
        status="PASS_DIAGNOSTIC_BOUNDS",
        scenarios=costs,
        cost_band_T2=on["paired_cost"]["T2_within_band"],
        ON_over_OFF=on["paired_cost"]["ON_over_OFF"],
        origin=phase,
        sources={
            "off": args.off_sha256,
            "on": args.on_sha256,
            "journal": header["journal_sha256"],
            "code": sha(Path(__file__)),
            "client_protocol": sha(HERE / "cliente.md"),
            "private_raw_manifest": args.archive_sha256,
            "wait_protocol": sha(HERE / "wait_bound.md"),
            "handoff_protocol": sha(HERE / "retorno.md"),
        },
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for opt in ("on", "off"):
        p.add_argument("--" + opt + "-dir", type=Path, required=True)
        p.add_argument("--" + opt + "-sha256", required=True)
    p.add_argument("--archive-manifest", type=Path, required=True)
    p.add_argument("--archive-sha256", required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(exist_ok=False)
    dest = args.new_output_dir / "receipt.json"
    try:
        report = execute(args)
    except Exception as exc:
        dest.write_text(json.dumps({"status": "FAIL", "gate": str(exc)}, indent=2) + "\n")
        raise
    dest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
