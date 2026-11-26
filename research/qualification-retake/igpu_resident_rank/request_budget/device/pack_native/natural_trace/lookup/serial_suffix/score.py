"""Budget a block prefix followed by a single-row suffix on the two real request clocks."""

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LOOKUP = run_path(str(HERE.parent / "screen.py"))
REPEAT_DIR = HERE.parents[1] / "prefill_retention/repeat"
REPEAT = run_path(str(REPEAT_DIR / "score.py"))
Q, T = REPEAT["Q"], REPEAT["T"]
check, digest, pinned = Q["check"], Q["digest"], Q["pinned"]
PROTOCOL = "b80da30364822148414d56781d4432f1cb5548e4c41e9f38d65911775dd0ef9a"
REPEAT_SHA = "3d52e5abce57d286c41edc6533756db5ef55e564bcc5a76620ae4cec5213447f"
P106 = "90750b0ccf87d7f5ceb6d89b6b320e1bf9cf07c0082c1961a31f14b67326aee9"


def decompose(calls, actions, spans):
    per_call = defaultdict(list)
    for number, layer, start, end in spans:
        check(1 <= number <= len(calls), "unowned callback")
        per_call[number].append((layer, start, end))
    result = []
    for i, (call, action) in enumerate(zip(calls, actions, strict=True), 1):
        enter, leave = call["enter_ns"], call["return_ns"]
        owned = per_call[i]
        check(call["number"] == i and enter < leave and owned, "missing observed call")
        prior = enter
        for _, start, end in owned:
            check(prior <= start <= end <= leave, "overlapping or escaped callback")
            prior = end
        if i > 2:
            check(
                [k for k, _ in itertools.groupby(x[0] for x in owned)] == list(range(36)),
                "unidentified single-row layer order",
            )
        verify = action in {"anchor", "skip"}
        charged = [x for x in owned if not verify or x[0] >= 25]
        remap = sum(end - start for _, start, end in charged)
        tail = leave - charged[0][1] if verify else 0
        result.append((action, leave - enter, tail, remap))
    return result


def price(rows, elapsed, target, keep_tail):
    removed = sum(duration for action, duration, _, _ in rows if action in {"anchor", "skip"})
    verified_rows = [r for r in rows if r[0] in {"anchor", "skip"}]
    suffix = sum(tail if keep_tail else remap for _, _, tail, remap in verified_rows)
    eligible = sum(remap for _, _, _, remap in rows)
    anchors = sum(action == "anchor" for action, *_ in rows)
    projected = elapsed - removed + suffix
    check(anchors and sum(r[1] for r in rows) <= elapsed and eligible <= projected, "clock cover")
    fraction = max(0, projected - target) / eligible if eligible else None
    return {
        "observed_ns": elapsed,
        "target_ns": target,
        "attempts": anchors,
        "ordinary_calls": len(rows) - len(verified_rows),
        "serial_known_rows": len(verified_rows),
        "removed_whole_verified_calls_ns": removed,
        "retained_suffix_ns": suffix,
        "eligible_remap_ns": eligible,
        "eligible_suffix_remap_ns": sum(r[3] for r in verified_rows),
        "required_fraction": fraction,
        "fractions": {
            str(p): {
                "projected_ns": projected - (p * eligible + 99) // 100,
                "total_available_ns": target - projected + (p * eligible + 99) // 100,
                "uniform_ns_per_attempt": (target - projected + (p * eligible + 99) // 100)
                // anchors,
            }
            for p in (0, 50, 100)
        },
    }


def process(arm, receipt, events, reference):
    host = T["NATIVE"]["host_trace"](events)
    calls = host["calls"]
    check(len(calls) == 48 and host["route"] == reference["route"], "routed work")
    cut = REPEAT["CLIENT"]["inspect"](arm, receipt, calls)
    check(
        cut == reference["client_cut"] and (cut["sample_call"], cut["sample_number"]) == (46, 45),
        "client-to-producer cut",
    )
    for name, field in (
        ("T2-result.json", "T2_result_sha256"),
        ("T2-request.jsonl", "T2_client_sha256"),
    ):
        check(digest(arm / "raw" / name) == reference[field], "same terminal clock")
    log = (arm / "raw" / receipt["native_ids"]["raw_stderr_file"]).read_bytes()
    check(T["mapping"](log, events)[0][25] == "CUDA0", "actual tier split")
    actions = LOOKUP["partition"](arm, receipt)
    rows = decompose(calls, actions, T["intervals"](events, host["callback_spans"]))
    scenarios = {}
    for name, keep in (("suffix_to_return", True), ("suffix_callbacks_only", False)):
        first = price(rows[:46], reference["first_final_ns"], 10**10, keep)
        decode = price(rows[2:], reference["decode_ns"], (47 * 10**9 + 5) // 6, keep)
        scenarios[name] = dict(
            first=first,
            decode=decode,
            joint_required_fraction=max(first["required_fraction"], decode["required_fraction"]),
        )
    return scenarios


def assess(old, new):
    reference = pinned(REPEAT_DIR / "receipt.json", REPEAT_SHA)
    check(digest(HERE / "protocol.md") == PROTOCOL, "frozen protocol")
    _, _, old_receipt, old_audit = Q["CHAIN"]["chain"](old, Q["P97"])
    old_rows, header = T["PFJ"]["read_journal"](old / "ON/raw/events.pfj")
    check(header == old_audit["header"], "historical journal receipt")
    _, new_rows, _, _ = Q["read_new"](new, P106)
    family = pinned(new / "family.json", P106)
    meta = pinned(new / "ON/arm.json", family["arms"]["ON"]["sha256"])
    new_receipt = pinned(new / "ON/receipt.json", meta["receipt_sha256"])
    return {
        "status": "TRACE_DERIVED_SPLIT_FIXED_PRICES",
        "protocol_sha256": PROTOCOL,
        "source_sha256": digest(Path(__file__)),
        "clock_reference_sha256": REPEAT_SHA,
        "families": {"P97": Q["P97"], "P106": P106},
        "P97": process(old / "ON", old_receipt, old_rows, reference["P97"]),
        "P106": process(new / "ON", new_receipt, new_rows, reference["new"]),
    }


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--p97", type=Path, required=True)
    args.add_argument("--p106", type=Path, required=True)
    args.add_argument("--new-output-dir", type=Path, required=True)
    opt = args.parse_args()
    opt.new_output_dir.mkdir(mode=0o700)
    try:
        report = assess(opt.p97, opt.p106)
    except Exception as exc:
        report = {"status": "INCONCLUSIVE", "error": type(exc).__name__, "reason": str(exc)}
    (opt.new_output_dir / "receipt.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n"
    )
    print(report["status"])
    raise SystemExit(int(report["status"] == "INCONCLUSIVE"))
