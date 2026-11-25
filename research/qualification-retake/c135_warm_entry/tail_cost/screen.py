"""Conditional CPU suffix price for C135's strictly serial (call, layer) service groups."""

import argparse
import hashlib
import json
import resource
import signal
import sys
from fractions import Fraction
from pathlib import Path

PROTOCOL = "a96b9424f3396d60149fc058aa4d2a18ab67e74f0cfc3fbd9bd9a5810010b54d"
PRIOR = "5250bcfef94731a8ccdba0056c8bdebc9dd1e47faca42f3160ec86ee820271e7"
PROGRAM = "53e9d8bdbac790a2657ccaed4b4ee2821c391b23680d627ea9b3292d70813fb7"
BUDGET_US = Fraction(2_427_104_435, 1000)
K = 378


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pinned(path, digest):
    content = path.read_bytes()
    require(hashlib.sha256(content).hexdigest() == digest, "changed " + path.name)
    return content


def keep(table, key, cost):
    if key not in table or cost < table[key]:
        table[key] = cost


def call_options(prices, cpu, charge):
    remaining = sorted(prices, reverse=True)
    require(all(type(x) is int and x >= 0 for x in remaining), "nonnegative whole READ prices")
    total = sum(remaining)
    for credits, longest in enumerate(remaining):
        yield credits, int(cpu), max(total, 4 * longest) if charge else 0
        total -= longest
    yield len(remaining), 0, 0


def read_curve(layers, capacity, free_cuda=False):
    """n -> minimum READ in quarter-us over all placements leaving n CPU groups nonempty."""
    require(type(capacity) is int and capacity >= 0, "capacity")
    states = {(0, 0): 0}
    for cpu, unknown, first, second in layers:
        require(type(cpu) is bool and type(unknown) is int and unknown >= 0, "layer schema")
        charge = cpu or not free_cuda
        second_options = list(call_options(second, cpu, charge))
        options = {}
        for i, a, t in call_options(first, cpu, charge):
            for j, b, u in second_options:
                used = max(0, i + j - unknown)
                if used <= capacity:
                    keep(options, (used, a + b), t + u)
        combined = {}
        for (old_k, old_n), old_t in states.items():
            for (added, groups), cost in options.items():
                used = old_k + added
                if used <= capacity:
                    keep(combined, (used, old_n + groups), old_t + cost)
        states = combined
    frontier = {}
    for (_, n), cost in states.items():
        keep(frontier, n, cost)
    return frontier


def exact(x):
    return dict(numerator=x.numerator, denominator=x.denominator, decimal_us=float(x))


def decision(curve, scale, budget):
    read = {n: scale * Fraction(r, 4) for n, r in curve.items()}
    low = min(read.values())
    result = dict(minimum_nonempty_cpu_groups=min(read), at_zero_us=exact(low),
                  optimal_groups_at_zero=sorted(n for n, v in read.items() if v == low))
    if low > budget:
        return dict(result, status="ALREADY_EXCLUDED_AT_ZERO", first_excluding_integer_us=0)
    if 0 in read and read[0] <= budget:
        return dict(result, status="NO_FINITE_CUTOFF")
    maximum = max((budget - cost) / n for n, cost in read.items() if n)
    last = maximum.numerator // maximum.denominator

    def floor(tau):
        return min(cost + n * tau for n, cost in read.items())

    require(floor(maximum) == budget and floor(last) <= budget < floor(last + 1), "cutoff proof")
    return dict(result, status="FINITE_CONDITIONAL_CUTOFF", supremum_us=exact(maximum),
                last_admissible_integer_us=last, first_excluding_integer_us=last + 1,
                floor_last_us=exact(floor(last)), floor_first_excluding_us=exact(floor(last + 1)),
                optimal_groups_at_cutoff=sorted(n for n, v in read.items()
                                                if v + n * maximum == budget))


def inputs(repo, trace, pr45):
    unit = repo / "research/qualification-retake"
    old = unit / "c135_warm_entry"
    reference = json.loads(pinned(old / "evidence/receipt.json", PRIOR))
    pinned(old / "screen.py", PROGRAM)
    sys.path.insert(0, str(unit))
    from c135_warm_entry import screen as warm

    require(warm.run(repo, trace, pr45) == reference, "complete warm-entry reproduction")
    from prefill_entry40 import screen as slots

    _, rows = slots.free.trace_rows(trace)
    start = slots.reconstruct(rows)[slots.CUTS[0]]
    service = json.loads(pinned(unit / "prefill_read_floor/replay-r2/receipt.json", warm.SERVICE))
    prices = warm.components(rows, service)
    first = {}
    for r in rows:
        if r["call_id"] in (1, 2) and r["kind"] == "DEMAND":
            first.setdefault((r["layer"], r["expert"]), r["call_id"])
    require(len(first) == reference["distinct_demands"], "demand census")
    layers, cold = [], [0, 0]
    for layer, occupants in enumerate(start):
        present = slots.resident(occupants)
        calls = ([], [])
        for key, call in first.items():
            if key[0] == layer and key[1] not in present:
                calls[call - 1].append(prices[key])
        unknown = occupants.count(None)
        cpu = layer < 25
        cold[int(not cpu)] += max(0, sum(map(len, calls)) - unknown)
        layers.append((cpu, unknown, *calls))
    require(cold == [553, 287] and len(layers) == 36
            and sum(x[1] for x in layers) == 16, "starting service census")
    return reference, layers


def run(repo, trace, pr45):
    pinned(Path(__file__).with_name("protocol.md"), PROTOCOL)
    reference, layers = inputs(repo, trace, pr45)
    modes = {}
    for mode, free_cuda in [("original_read", False), ("cuda_read_free", True)]:
        curve = read_curve(layers, K, free_cuda)
        scales = {}
        for label, scale in [("1.0", Fraction(1)), ("0.8", Fraction(4, 5))]:
            r = decision(curve, scale, BUDGET_US)
            if not free_cuda:
                expected = reference["strict_layer_major"][label]["by_capacity"][str(K)]
                require(abs(r["at_zero_us"]["decimal_us"] - expected["floor_s"] * 1e6) < 1e-6,
                        "zero suffix must reproduce previous floor")
            scales[label] = r
        modes[mode] = dict(
            minimum_read_quarter_us_by_nonempty_cpu_groups=dict(sorted(curve.items())),
            scales=scales,
        )
    require(modes["original_read"]["minimum_read_quarter_us_by_nonempty_cpu_groups"].keys()
            == modes["cuda_read_free"]["minimum_read_quarter_us_by_nonempty_cpu_groups"].keys(),
            "changing CUDA prices changes placement cost, not eligibility")
    return dict(status="REPRODUCED_CONDITIONAL_CPU_SUFFIX_PRICE",
                program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                protocol_sha256=PROTOCOL, prior_receipt_sha256=PRIOR,
                c135_sha256=reference["trace_sha256"], pr45=reference["pr45"],
                additional_entries=K, cpu_layers=25, cuda_layers=11, calls=[5, 148],
                budget_us=exact(BUDGET_US), modes=modes, gpu_used=False, weight_reads=0,
                model_forwards=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "trace", "pr45-checkout", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (384 << 20, 384 << 20))
    signal.alarm(120)
    args.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        result = run(args.repo.resolve(), args.trace.resolve(), args.pr45_checkout.resolve())
    except FileNotFoundError as exc:
        result = dict(status="NOT_RUN_RAW_REQUIRED", file=Path(exc.filename).name)
    except (ValueError, OSError, KeyError, MemoryError) as exc:
        result = dict(status="INCONCLUSIVE_PRESERVED", reason=str(exc))
    output = json.dumps(result, indent=2, allow_nan=False) + "\n"
    require(len(output.encode()) <= 2 << 20, "receipt limit")
    pending = args.new_output_dir / ".pending"
    pending.write_text(output)
    pending.rename(args.new_output_dir / "receipt.json")
    return int(result["status"] != "REPRODUCED_CONDITIONAL_CPU_SUFFIX_PRICE")


if __name__ == "__main__":
    raise SystemExit(main())
