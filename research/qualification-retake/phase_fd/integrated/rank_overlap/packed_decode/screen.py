"""Bound same-wave rank overlap with the service observed in two packed C291 conversations."""

import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NATURAL = HERE.parents[3] / "igpu_resident_rank/request_budget/device/pack_native/natural_trace"
ORIGINAL = HERE.parent / "screen.py"
ACCOUNTING = NATURAL / "prefill_retention/request_cost/score.py"
OVERLAP, C = run_path(str(ORIGINAL)), run_path(str(ACCOUNTING))
Q, T, check = C["Q"], C["T"], C["check"]
METHOD = "4c31bb9ec0d4637be7dbcd3fcdd5f9c38c31e0267c759819568465240901f934"
DEFAULT = "0aa8aa7e9fcc37a487777163be61d8de3107300d595ceb596998b1aa2cc4bb7f"
COMPARISON = "bdd8a06f8694efccbd5282db0b73b222768d328f8263e431c694dcbadddb991c"
NS = 10**9
PHASES = ("prefill5", "prefill148", "decode_early", "decode_tail")


def clocks(first, decode, prefill_credit, early_credit, tail_credit):
    first_floor = first - prefill_credit - early_credit
    decode_floor = decode - early_credit - tail_credit
    check(first_floor >= 0 and decode_floor > 0, "credit exceeds source clock")
    fm, dm = 10 * NS - first_floor, 47 * NS // 6 - decode_floor
    return dict(
        first_gain_ns=prefill_credit + early_credit,
        decode_gain_ns=early_credit + tail_credit,
        first_floor_ns=first_floor,
        decode_floor_ns=decode_floor,
        first_margin_ns=fm,
        decode_margin_ns=dm,
        conditional_decode_ceiling_tps=47 * NS / decode_floor,
        first_additional_cost_ceiling_ns=max(0, fm),
        decode_additional_cost_ceiling_ns=max(0, dm),
        edge_shared_cost_ceiling_ns=max(0, min(fm, dm)),
        joint="HEADROOM_ONLY" if min(fm, dm) >= 0 else "NO_GO_FIXED_SCENARIO",
    )


def intervals(waves, ready, tiers):
    totals = defaultdict(Counter)
    for i, w in enumerate(waves):
        after = waves[i + 1] if i + 1 < len(waves) else None
        metrics = OVERLAP["opportunity"](w, after, ready)
        phase = (
            PHASES[0]
            if w.call == 1
            else PHASES[1]
            if w.call == 2
            else PHASES[2]
            if w.call <= 46
            else PHASES[3]
        )
        totals[phase, tiers[w.layer]].update(metrics)
    return totals


def price_modes(totals, first, decode):
    modes = {}
    for phases, scope in ((PHASES[2:], "decode"), (PHASES, "prefill_and_decode")):
        for tiers, target in ((["CPU"], "CPU"), (["CPU", "CUDA0"], "CPU_and_CUDA")):
            cases = {}
            for key in ("resident", "progressive"):
                credit = {
                    p: sum(totals[p, t][key + "_upper_ns"] for t in tiers) if p in phases else 0
                    for p in PHASES
                }
                cases[key] = clocks(
                    first,
                    decode,
                    credit["prefill5"] + credit["prefill148"],
                    credit["decode_early"],
                    credit["decode_tail"],
                )
            modes[scope + "/" + target] = cases
    return modes


def analyse(root, receipt, rows, tiers):
    arm = root / "ON"
    host = C["NATIVE"]["host_trace"](rows)
    cut = C["CLIENT"]["inspect"](arm, receipt, host["calls"])
    check((cut["sample_number"], cut["sample_call"]) == (45, 46), "first final edge")
    maximum = host["calls"][45]["return_ns"] + cut["last_relevant_return_to_first_final_ns"]
    minimum = maximum - abs(cut["first_frame_minus_metric_ns"]) - 2
    wav, ready = OVERLAP["collect"](rows, 1)
    official = Q["L"]["ranks"](rows, 1)
    service, jobs = C["timeline"](rows)
    check(
        len(official) == 7012 and len(jobs) == 2354 and len(service) == len(wav) == 2987,
        "work denominators",
    )
    check([(w.call, w.begin, w.end) for w in wav] == host["callback_spans"], "remap correspondence")
    operated = hashlib.sha256()
    for w, s in zip(wav, service, strict=True):
        site = (w.call, w.tile, w.layer, w.ordinal)
        check(
            s.site == site and s.demands == set(w.demand) and len(w.demand) == len(s.demands),
            "slot generation demand",
        )
        if w.call > 2:
            ranks = official[w.call - 1, w.tile, w.layer, 0]
            check(
                w.nrows == 1 and len(w.demand) == 4 and {k[3] for k in w.demand} == set(ranks),
                "decode: rank/demand identity",
            )
        check(w.end <= minimum if w.call <= 46 else w.begin >= maximum, "ambiguous client split")
        for k in sorted(w.demand):
            operated.update(struct.pack("<8q", *site, *k))
    log = arm / "raw" / receipt["native_ids"]["raw_stderr_file"]
    check(
        C["digest"](log) == receipt["native_ids"]["stderr_sha256"]
        and tiers
        == T["mapping"](log.read_bytes(), rows)[0]
        == {i: ("CPU" if i < 25 else "CUDA0") for i in range(36)},
        "own device placement",
    )
    totals = intervals(wav, ready, tiers)
    for p, count in (("decode_early", 44), ("decode_tail", 2)):
        check(
            totals[p, "CPU"]["waves"] == count * 25 and totals[p, "CUDA0"]["waves"] == count * 11,
            "44/2 decode population",
        )
    client = json.loads((arm / "raw/T2-result.json").read_bytes())
    first = int(Decimal(str(client["stream_metrics"]["first_final_content_chunk_s"])) * NS)
    decode = int(Decimal(str(client["timings"]["predicted_ms"])) * 10**6)
    pub = receipt["rows"][1]
    check(
        pub["functional"] == "PASS"
        and pub["cache_n"] == 2044
        and pub["prompt_n"] == client["timings"]["prompt_n"] == 153
        and pub["predicted_n"] == client["timings"]["predicted_n"] == 47
        and abs(first - pub["first_final_s"] * NS) < 2
        and abs(decode - pub["decode_s"] * NS) < 2,
        "client and server clocks",
    )
    return dict(
        first_final_ns=first,
        decode_ns=decode,
        sample=cut["sample_number"],
        call=cut["sample_call"],
        observed_gap_first_ns=first - 10 * NS,
        observed_gap_decode_ns=decode - 47 * NS // 6,
        t2_sha256=C["digest"](arm / "raw/T2-result.json"),
        ops_sha256=operated.hexdigest(),
        route=host["route"],
        handoff=host["first_decode"],
        source_work=dict(reservations=len(jobs), quartets=len(official), remaps=len(wav)),
        phase_by_tier={p: {t: dict(totals[p, t]) for t in ("CPU", "CUDA0")} for p in PHASES},
        scopes=price_modes(totals, first, decode),
    )


def run(archive):
    digest, pinned = C["digest"], C["pinned"]
    check(
        digest(HERE / "protocol.md") == METHOD
        and digest(ORIGINAL) == DEFAULT
        and digest(ACCOUNTING) == COMPARISON,
        "frozen source",
    )
    arms, provenance = {}, {}
    for label, (name, family_sha, manifest_sha) in C["SOURCES"].items():
        part = archive / ("part-" + label[1:])
        root = part / name
        manifest = pinned(part / "manifest.json", manifest_sha)
        C["authenticate_raw"](root, manifest, ["raw/T2-result.json", "raw/T2-request.jsonl"])
        if label == "P106":
            _, rows, tiers, info = Q["read_new"](root, family_sha)
            a = pinned(root / "family.json", family_sha)["arms"]["ON"]["arm"]
            receipt = pinned(root / "ON/receipt.json", a["receipt_sha256"])
            journal_sha = info["journal_sha256"]
        else:
            _, a, receipt, stored = C["CHAIN"]["chain"](root, family_sha)
            checked = C["NATIVE"]["audit_arm"](
                root / "ON", receipt, receipt["pack_events"]["before_second_ns"]
            )
            check(
                json.loads(json.dumps(checked)) == stored and stored["jobs"]["eligible_clean_run"],
                "P97 service audit",
            )
            rows, hdr = T["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
            journal_sha = hdr["journal_sha256"]
            tiers = T["mapping"](
                (root / "ON/raw" / receipt["native_ids"]["raw_stderr_file"]).read_bytes(), rows
            )[0]
        check(len(Q["bindings"](rows)) == 1440, "initial pools")
        arms[label] = analyse(root, receipt, rows, tiers)
        provenance[label] = dict(
            manifest_sha256=manifest_sha,
            family_sha256=family_sha,
            arm_receipt_sha256=a["receipt_sha256"],
            journal_sha256=journal_sha,
        )
        del rows
    for k in ("ops_sha256", "route", "handoff", "source_work"):
        check(arms["P97"][k] == arms["P106"][k], "different routed work or carry: " + k)
    return dict(
        status="TRACE_DERIVED_PACK_RANK_OVERLAP",
        protocol_sha256=METHOD,
        program_sha256=digest(HERE / "screen.py"),
        sources=provenance,
        arms=arms,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("archive", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.archive)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", error=type(exc).__name__, reason=str(exc))
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
