"""Price two interventions on the same confirmed conversation using disjoint native spans."""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
REOPEN = run_path(str(HERE.parent / "release/run.py"))
NATURAL = REOPEN["NATURAL"]
check = NATURAL["check"]
HISTORY = HERE.parents[5] / "history_lookup/native_ids"


def partition(arm, receipt):
    verified = run_path(str(HISTORY / "verify.py"))
    replay = run_path(str(HISTORY / "b3_fixture/run.py"))
    oracle = json.loads((HISTORY / "evidence/b3.json").read_bytes())
    name = receipt["native_ids"]["raw_stderr_file"]
    check(Path(name).name == name, "producer name")
    log = (arm / "raw" / name).read_bytes()
    check(
        hashlib.sha256(log).hexdigest() == receipt["native_ids"]["stderr_sha256"], "producer hash"
    )
    samples = [token for token, _ in verified["trajectories"](log)[1]]
    prompt = verified["projection"](arm / "raw", 2, verified["GEOMETRY"][1])[0]["official_ids"]
    for seq, key in ((prompt, "prompt_i32_sha256"), (samples, "sampled_i32_sha256")):
        check(hashlib.sha256(verified["ids_bytes"](seq)).hexdigest() == oracle[key], key)
    labels = []
    for action in replay["trace"](replay["python_rule"](), prompt, samples, 46):
        check(action["position"] == len(labels) and action["emitted"] >= 1, "causal action")
        labels.append("ar" if action["ar"] else "anchor")
        labels.extend(["skip"] * (action["emitted"] - 1))
    check(Counter(labels) == {"ar": 23, "anchor": 11, "skip": 12}, "full decode actions")
    check(Counter(labels[:44]) == {"ar": 23, "anchor": 10, "skip": 11}, "first final actions")
    return ["prefill", "prefill", *labels]


def savings(calls, spans, actions):
    remaps = defaultdict(list)
    for idx, start, end in spans:
        check(1 <= idx <= len(calls), "foreign remap")
        remaps[idx].append((start, end))
    check(len(calls) == len(actions), "action count")
    rows = []
    previous = 0
    for idx, (call, action) in enumerate(zip(calls, actions, strict=True), 1):
        start, end = call["enter_ns"], call["return_ns"]
        check(call["number"] == idx and previous <= start <= end, "call nesting/order")
        previous = end
        tail = start
        credit = 0
        for a, b in remaps[idx]:
            check(tail <= a <= b <= end, "overlap or escaped remap")
            credit += b - a
            tail = b
        check(action in {"prefill", "ar", "anchor", "skip"}, "unknown position")
        rows.append((action, end - start, credit))
    return rows


def price(rows, observed, target, all_gaps_free):
    inside = sum(duration for _, duration, _ in rows)
    check(inside <= observed, "native intervals exceed clock")
    removed = sum(d for tag, d, _ in rows if tag in ("anchor", "skip"))
    retained_remap = sum(r for tag, _, r in rows if tag in ("prefill", "ar"))
    anchor_count = sum(tag == "anchor" for tag, _, _ in rows)
    check(anchor_count > 0, "missing verification")
    base = (inside if all_gaps_free else observed) - removed
    need = max(0, base - target)
    rows_by_fraction = {}
    for percent in (0, 50, 100):
        # Grant a fractional nanosecond of savings to the candidate.
        cost = base - (retained_remap * percent + 99) // 100
        margin = target - cost
        rows_by_fraction[str(percent)] = {
            "projected_ns": cost,
            "budget_for_all_verification_and_overheads_ns": margin,
            "uniform_ns_per_verification": margin // anchor_count,
        }
    return {
        "observed_ns": observed,
        "target_ns": target,
        "native_call_envelopes_ns": inside,
        "outside_ns": observed - inside,
        "fully_credited_call_ns": removed,
        "eligible_retained_remap_ns": retained_remap,
        "anchors_to_charge": anchor_count,
        "required_remap_ns_at_free_verification": need,
        "required_fraction": (need / retained_remap if retained_remap else (None if need else 0)),
        "fractions": rows_by_fraction,
    }


def together(first, decode):
    joint = {}
    for pct, f in first["fractions"].items():
        d = decode["fractions"][pct]
        max_price = min(f["uniform_ns_per_verification"], d["uniform_ns_per_verification"])
        joint[pct] = {
            "signed_uniform_ns_per_verification_and_coordination": max_price,
            "status": "HEADROOM_ONLY" if max_price >= 0 else "NO_GO_FIXED_PRICES",
        }
    required = [s["required_fraction"] for s in (first, decode)]
    return {
        "first_final": first,
        "decode": decode,
        "both_targets": joint,
        "joint_required_fraction_at_free_verification": (
            max(required) if all(v is not None for v in required) else None
        ),
    }


def assess(root, family_hash):
    family, arm, receipt, original = REOPEN["chain"](root, family_hash)
    on = root / "ON"
    audit = NATURAL["audit_arm"](on, receipt, receipt["pack_events"]["before_second_ns"])
    check(json.loads(json.dumps(audit)) == original, "natural audit equality")
    check(
        audit["status"] == "PASS_PACK_NATURAL_TRACE" and audit["jobs"]["status"] == "COMPLETE",
        "incomplete observation",
    )
    check(
        audit["http_cut"]["sample_call"] == 46 and audit["http_cut"]["sample_number"] == 45,
        "first final not identified",
    )
    events, _ = NATURAL["PFJ"]["read_journal"](on / "raw/events.pfj")
    host = NATURAL["host_trace"](events)
    rows = savings(host["calls"], host["callback_spans"], partition(on, receipt))
    public = receipt["rows"][1]
    # Round observed durations down and allowable decode time up, favouring both interventions.
    f, d = (math.floor(public[k] * 1e9) for k in ("first_final_s", "decode_s"))
    scenarios = {}
    for key, gaps_free in (("fixed_outside", False), ("free_outside", True)):
        first = price(rows[:46], f, 10_000_000_000, gaps_free)
        decode = price(rows[2:], d, (47_000_000_000 + 5) // 6, gaps_free)
        scenarios[key] = together(first, decode)
    return {
        "status": "TRACE_DERIVED_COMBINED_CONDITIONAL",
        "family_sha256": family_hash,
        "arm_sha256": family["arms"]["ON"]["sha256"],
        "journal_sha256": audit["header"]["journal_sha256"],
        "receipt_sha256": arm["receipt_sha256"],
        "route": audit["route"],
        "transfer": family["paired"]["clock_transfer"],
        "scenarios": scenarios,
        "sources": {
            str(path.relative_to(HERE.parents[5])): REOPEN["digest"](path)
            for path in (
                HERE / "protocol.md",
                Path(__file__),
                HISTORY / "verify.py",
                HISTORY / "b3_fixture/run.py",
                HISTORY / "evidence/b3.json",
            )
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family-dir", required=True, type=Path)
    parser.add_argument("--family-sha256", required=True)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        answer = assess(args.family_dir, args.family_sha256)
    except Exception as exc:
        frame = exc.__traceback__
        while frame.tb_next:
            frame = frame.tb_next
        answer = {
            "status": "FAIL_PRESERVED",
            "family_sha256": args.family_sha256,
            "error": type(exc).__name__,
            "where": [Path(frame.tb_frame.f_code.co_filename).name, frame.tb_lineno],
        }
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(answer, f, indent=2, sort_keys=True)
        f.write("\n")
    print(answer["status"])
    raise SystemExit(int(answer["status"] == "FAIL_PRESERVED"))
