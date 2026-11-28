"""Substitute one prefill duration and disjoint target intervals, preserving both W clocks."""

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "evidence-20261128-r01/study.json"
WAVE = HERE.parents[1] / "layer/prefix/wave/evidence-tier-20261128-r01/receipt.json"


def read(path):
    return json.loads(path.read_bytes())


def need(ok, why):
    if not ok:
        raise ValueError(why)


def capped(row, w, stop, cost, measured, limit):
    ticks = w["ticks_ns"]
    covered = 0
    blocks = 0
    emitted = 0
    overhead = row["prep_ns"]
    for (at, width, depth, count), (lookup, update) in zip(
        row["rows"], row["timing_ns"], strict=True
    ):
        lo = at - 1
        need(
            emitted == lo and depth <= width and count in (depth, depth + 1) and count >= 1,
            "target ledger",
        )
        hi = lo + count
        need(count == depth + 1 or hi == len(ticks) - 1, "EOG-only truncation")
        if lo < stop:
            overhead += lookup + update
            if width:
                blocks += 1
                covered += ticks[min(hi, stop)] - ticks[lo]
        emitted = hi
    need(emitted == len(ticks) - 1, "incomplete target")
    fixed = measured + cost - covered + overhead
    return dict(
        blocks=blocks,
        covered_serial_ns=covered,
        controller_ns=overhead,
        free_target_ns=fixed,
        max_target_ns_per_block=(limit - fixed) // blocks if blocks else None,
    )


def calculate(replays, study, tier):
    need(
        len(replays) == 2 and all(r["status"] == "REPRODUCED_CAUSAL_EOG" for r in replays),
        "two independent replays",
    )
    cases = study["evidence"]["clocks"]
    phases = {
        k: v["trained"]["copied"]["limits_by_Bps"]["4500000000"]["prefill_ns"]
        for k, v in tier["result"]["arms"].items()
    }
    result = {}
    for method in ("N2", "majority"):
        rows = []
        for name in ("nominal", "code"):
            a, b = (r["cases"][name][method] for r in replays)
            need(
                a["rows"] == b["rows"] and a["decisions_sha256"] == b["decisions_sha256"],
                "causal schedule changed",
            )
            for rep, controller in enumerate((a, b), 1):
                for w in cases[name]:
                    prices = phases if name == "nominal" else {"W": w["prefill_ns"]}
                    for source, prefill in prices.items():
                        n = len(w["ticks_ns"])
                        first = capped(
                            controller,
                            w,
                            w["cut"],
                            prefill - w["prefill_ns"],
                            w["first_final_ns"],
                            10**10 if name == "nominal" else w["first_final_ns"],
                        )
                        decode = capped(
                            controller,
                            w,
                            n - 1,
                            0,
                            w["decode_ns"],
                            n * 10**9 // 6 if name == "nominal" else w["decode_ns"],
                        )
                        # Retain the measured interval between decode and response validation.
                        valid = capped(
                            controller,
                            w,
                            n - 1,
                            prefill - w["prefill_ns"],
                            w["valid_ns"],
                            w["valid_ns"],
                        )
                        joint = min(
                            first["max_target_ns_per_block"], decode["max_target_ns_per_block"]
                        )
                        if name == "code":
                            joint = min(joint, valid["max_target_ns_per_block"])
                        rows.append(
                            dict(
                                case=name,
                                W=w["arm"],
                                replay=rep,
                                prefill_source=source,
                                prefill_ns=prefill,
                                first=first,
                                decode=decode,
                                valid=valid,
                                joint_max_target_ns=joint,
                            )
                        )
        counts = {}
        for n in cases:
            model = replays[0]["cases"][n][method]
            widths = [r for r in model["rows"] if r[1]]
            counts[n] = dict(
                blocks=len(widths),
                proposed=sum(r[1] for r in widths),
                accepted=sum(r[2] for r in widths),
                target_ids=len(cases[n][0]["ticks_ns"]),
                first_final_sample=cases[n][0]["cut"] + 1,
            )
        worst = min(r["joint_max_target_ns"] for r in rows)
        result[method] = dict(
            cases=counts,
            arms=rows,
            min_max_target_ns=worst,
            decision="NO_GO_EVEN_FREE_TARGET" if worst < 0 else "CONDITIONAL_HEADROOM_ONLY",
        )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--replays", type=Path, nargs=2)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    if a.new_output_dir:
        a.new_output_dir.mkdir(mode=0o700)
    try:
        if a.replays:
            receipts = [read(p / "receipt.json") for p in a.replays]
        else:
            receipts = read(a.check)["receipts"]
        sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (PREVIOUS, WAVE)}
        score = calculate(receipts, read(PREVIOUS), read(WAVE))
        result = dict(result=score, sources=sources, receipts=receipts)
        if a.check:
            need(read(a.check) == result, "different result")
        else:
            with (a.new_output_dir / "receipt.json").open("x") as f:
                json.dump(result, f, separators=(",", ":"), sort_keys=True)
        print({k: r["decision"] for k, r in score.items()})
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc)))
            )
        raise
