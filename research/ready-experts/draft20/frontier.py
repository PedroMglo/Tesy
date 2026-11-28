"""Tight first-content and full-decode constraints on the same atomic-block schedule."""

import argparse
import json
from pathlib import Path
from statistics import median


def path_options(case, w, mode, price):
    ticks, cut = w["ticks_ns"], w["cut"]
    n = len(ticks) - 1
    match, ns = case["serial_matches"], case["serial_ns"]
    if len(match) != n or len(ns) != n or price < 0:
        raise ValueError("incompatible draft and W clock")

    def edges(i):
        yield i + 1, "S", ticks[i + 1] - ticks[i]
        if i + 3 <= n or case.get("issue_through_eog", False):
            # The target may stop at a matched EOG, before the second ID or the bonus.
            second = i + 1 < n
            depth = (
                min(2, n - i)
                if mode == "perfect"
                else int(match[i]) * (1 + int(second and match[i + 1]))
            )
            cost = price
            if mode == "paid":
                cost += ns[i] + (ns[i + 1] if depth and second else 0)
            yield min(n, i + 1 + depth), "B" + str(depth), cost

    # At each first arrival j >= cut a different initial state of the suffix may be left.
    # Earlier IDs have no further state in this optimistic, fixed-price model.
    prefix = {0: (0, ())}
    for i in range(cut):
        elapsed, history = prefix[i]
        for j, kind, cost in edges(i):
            option = elapsed + cost, history + (kind,)
            if j not in prefix or option < prefix[j]:
                prefix[j] = option
    suffix = {n: (0, ())}
    for i in reversed(range(cut, n)):
        suffix[i] = min((cost + suffix[j][0], (kind,) + suffix[j][1]) for j, kind, cost in edges(i))
    first_external = w["first_final_ns"] - ticks[cut]
    decode_external = w["decode_ns"] - ticks[-1]
    options = []
    for j in sorted(prefix):
        if j >= cut:
            end = prefix[j][0] + suffix[j][0]
            options.append(
                dict(
                    first_ns=first_external + prefix[j][0],
                    decode_ns=decode_external + end,
                    crossing_index=j,
                    path=list(prefix[j][1] + suffix[j][1]),
                )
            )
    return options


def best(case, w, mode, price):
    limit = len(w["ticks_ns"]) * 10**9 // 6
    options = path_options(case, w, mode, price)
    joint = [p for p in options if p["decode_ns"] <= limit]
    winner = min(
        joint or options,
        key=lambda p: (p["first_ns"], p["decode_ns"]) if joint else (p["decode_ns"], p["first_ns"]),
    )
    return dict(
        **winner,
        price_ns=price,
        decode_admitted=bool(joint),
        admitted=bool(joint) and winner["first_ns"] <= 10**10,
        min_first_any_decode_ns=min(p["first_ns"] for p in options),
        first_cut_reduction_needed_ns=max(0, winner["first_ns"] - 10**10) if joint else None,
    )


def frontier(case, w, mode):
    zero = best(case, w, mode, 0)
    n1 = int(median([b - a for a, b in zip(w["ticks_ns"][:-1], w["ticks_ns"][1:], strict=True)]))
    reference = best(case, w, mode, n1)
    if not zero["admitted"]:
        return dict(
            zero=zero, max_joint_price_ns=None, first_failing=zero, one_serial_price=reference
        )
    lo, hi = 0, 10**10 + 1
    if best(case, w, mode, hi)["admitted"]:
        raise ValueError("unbounded after granting the serial control")
    while hi - lo > 1:
        mid = (hi + lo) // 2
        if best(case, w, mode, mid)["admitted"]:
            lo = mid
        else:
            hi = mid
    return dict(
        zero=zero,
        max_joint_price_ns=lo,
        witness=best(case, w, mode, lo),
        first_failing=best(case, w, mode, hi),
        one_serial_price=reference,
    )


def evaluate(evidence):
    case = evidence["draft"]["nominal"]
    return [
        {mode: frontier(case, w, mode) for mode in ("perfect", "free", "paid")} | {"W": w["arm"]}
        for w in evidence["clocks"]["nominal"]
    ]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("study", type=Path)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--new-output-dir", type=Path)
    group.add_argument("--check", type=Path)
    a = p.parse_args()
    if a.new_output_dir:
        a.new_output_dir.mkdir(mode=0o700)
    try:
        got = evaluate(json.loads(a.study.read_bytes())["evidence"])
        if a.check:
            if got != json.loads(a.check.read_bytes()):
                raise ValueError("joint witnesses differ")
        else:
            with (a.new_output_dir / "receipt.json").open("x") as out:
                json.dump(got, out, sort_keys=True, separators=(",", ":"))
                out.write("\n")
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps({"status": "FAIL_PRESERVED", "reason": str(exc)}) + "\n"
            )
        raise
    print("REPRODUCED_JOINT_BLOCK_FRONTIER")
