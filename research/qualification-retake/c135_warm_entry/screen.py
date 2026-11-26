"""Optimistic C135 prefill service with a paid-or-granted set of additional starting identities."""
import argparse
import hashlib
import json
import resource
import signal
import sys
from collections import Counter, defaultdict
from itertools import accumulate
from pathlib import Path

PROTOCOL = "d02a1541f496d8c6ed1bb70bb9d2851669bb41484f4cf7539852ebe7e014c482"
ENTRY = "16291c82a97afeb320d537e7be81dddf8833b583add98ffcf868666dd1ce4901"
SERVICE = "f2cd36d9b060e4864de620aab05013fe462b9a581b86474a3d127abd1b66c8cf"
TRACE = "91610b12291d5a42a12bba09f5d4ff188d25ee0001ab89e894bdd508005e82fb"
SOURCE_ENTRY = "fc81af6d0a9e624af8909233324e9c094e5849ffc6f11b3c16477354322e0eb0"
SOURCE_CLOCK = "20ef296cf4d1dd78e1a3d6341e36d1bce2c53d46c87f59b7eb7d7dcf8279bfba"
PAYLOAD = 13_219_200
BUDGET_US = 2_427_104.435
SIZES = (0, 243, 378)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def checked(path, expected):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected, "digest " + path.name)
    return data


def group_curve(prices, layered):
    """Cost in quarter microseconds with 0..N free identities; exchange removes longest first."""
    values = sorted(prices, reverse=True)
    require(all(type(x) is int and x >= 0 for x in values), "nonnegative microseconds")
    sums = list(reversed(list(accumulate(reversed(values), initial=0))))
    return [max(s, 4 * longest) if layered else s
            for s, longest in zip(sums, [*values, 0], strict=True)]


def combine(a, b):
    """Minimum sum when exactly k credits can be split between two disjoint sets."""
    inf = sum((a[0], b[0])) + 1
    result = [inf] * (len(a) + len(b) - 1)
    for i, left in enumerate(a):
        for j, right in enumerate(b):
            if left + right < result[i + j]:
                result[i + j] = left + right
    return result


def frontier(groups, unknowns, layered):
    require(len(groups) == len(unknowns), "layer counts")
    result = [0]
    for (call5, call148), unknown in zip(groups, unknowns, strict=True):
        require(type(unknown) is int and unknown >= 0, "unknown slot count")
        both = combine(group_curve(call5, layered), group_curve(call148, layered))
        # Unknown slot identities are free only in their own layer, once across both returns.
        result = combine(result, both[min(unknown, len(both) - 1):])
    require(result[-1] == 0 and all(a >= b for a, b in zip(result, result[1:], strict=False)),
            "capacity order")
    return result


def components(rows, receipt):
    """Price the fastest complete same-key READ chain, without splicing three different jobs."""
    prices = {}
    for call, old in enumerate(receipt["calls"], 1):
        edges = defaultdict(dict)
        for r in rows:
            if r["call_id"] != call or r["kind"] not in ("READ_BEGIN", "READ_END"):
                continue
            key = tuple(r[k] for k in ("layer", "expert", "slot", "generation"))
            mark = (r["component"], r["kind"])
            require(r["logical_bytes"] == PAYLOAD // 3 and mark not in edges[key],
                    "component payload or identity")
            edges[key][mark] = r["mono_us"]
        total = 0
        for generation, records in edges.items():
            stamps = [records[i, kind] for i in range(3) for kind in ("READ_BEGIN", "READ_END")]
            require(len(records) == 6 and sorted(stamps) == stamps, "three successive reads")
            durations = [b - a for a, b in zip(stamps[0::2], stamps[1::2], strict=True)]
            total += sum(durations)
            conservative = sum(max(0, d - 1) for d in durations)
            key = generation[:2]
            prices[key] = min(conservative, prices.get(key, conservative))
        require(len(edges) == old["jobs"] and total == old["read_worker_us"],
                "C135 service conservation")
    return prices


def classify(curve):
    out = {}
    for scale in (0.8, 1.0):
        per_slot = [quarter * scale / 4 for quarter in curve]
        smallest = next(i for i, t in enumerate(per_slot) if t <= BUDGET_US)
        at_k = {}
        for k in SIZES:
            t = per_slot[min(k, len(per_slot) - 1)]
            at_k[str(k)] = dict(
                floor_s=t / 1e6, slack_s=(BUDGET_US - t) / 1e6,
                decision="NO_GO_CONDITIONAL" if t > BUDGET_US else "INCONCLUSIVE",
            )
        out[str(scale)] = dict(
            by_capacity=at_k, min_additional_entries=smallest,
            min_additional_payload_bytes=smallest * PAYLOAD,
            floor_at_cutoff_s=per_slot[smallest] / 1e6,
            floor_one_fewer_s=per_slot[smallest - 1] / 1e6 if smallest else None,
        )
    return out


def run(repo, trace, pr45):
    checked(Path(__file__).with_name("protocol.md"), PROTOCOL)
    base = repo / "research/qualification-retake"
    entry = json.loads(checked(base / "prefill_entry40/evidence/receipt.json", ENTRY))
    service = json.loads(checked(base / "prefill_read_floor/replay-r2/receipt.json", SERVICE))
    require(trace.stat().st_size == 3_603_647, "C135 trace length")
    checked(trace, TRACE)
    checked(base / "prefill_read_floor/bound.py", SOURCE_CLOCK)
    checked(base / "prefill_entry40/screen.py", SOURCE_ENTRY)
    sys.path.insert(0, str(base))
    from prefill_read_floor import bound

    # Verify the #45 modules before the slot helper imports tools of the same names.
    require(bound.run(trace, pr45) == service, "independent service receipt")
    from prefill_entry40 import screen as slots

    layers, rows = slots.free.trace_rows(trace)
    cuts = slots.reconstruct(rows)
    for cut, table in cuts.items():
        raw = json.dumps(table, separators=(",", ":")).encode()
        mark = f"{cut[0].lower()}_{cut[1]}"
        require(hashlib.sha256(raw).hexdigest() == entry["snapshot_sha256"][mark], "slot cut")
    start = cuts[slots.CUTS[0]]
    unknowns = [row.count(None) for row in start]
    require(sum(unknowns) == 16 and sum(len(slots.resident(r)) for r in start) == 1424,
            "C135 initial census")
    prices = components(rows, service)
    first = {}
    for r in rows:
        if r["call_id"] in (1, 2) and r["kind"] == "DEMAND":
            first.setdefault((r["layer"], r["expert"]), r["call_id"])
    require(len(first) == 1759 and set(prices) <= set(first), "demanded distinct keys")
    groups, by_tier, missing_prices, symbolic_only = [], Counter(), Counter(), Counter()
    for layer, slots_here in enumerate(start):
        tier = layers[layer]["device"]
        require(tier == ("CPU" if layer < 25 else "CUDA0")
                and layers[layer]["bytes"] == PAYLOAD, "tier or payload")
        resident = slots.resident(slots_here)
        needs = [key for key in first if key[0] == layer and key[1] not in resident]
        grouped = [[], []]
        for key in needs:
            grouped[first[key] - 1].append(prices.get(key, 0))
            if key not in prices:
                missing_prices[tier] += 1
        floor = max(0, len(needs) - unknowns[layer])
        require(floor == entry["layers"][layer]["distinct_floor"], "layer logical floor")
        symbolic_only[tier] += len(needs)
        by_tier[tier] += floor
        groups.append(grouped)
    require(dict(by_tier) == {"CPU": 553, "CUDA0": 287}, "tier distinct census")
    n = sum(by_tier.values())
    volume = frontier(groups, unknowns, layered=False)
    phase = frontier(groups, unknowns, layered=True)
    require(len(volume) == len(phase) == n + 1
            and all(a <= b for a, b in zip(volume, phase, strict=True)),
            "nested floors")
    max_bytes = BUDGET_US * 4500
    byte_cutoff = max(0, n - int(max_bytes // PAYLOAD))
    return dict(
        status="REPRODUCED_C135_CONDITIONAL_FLOORS",
        trace_sha256=TRACE, protocol_sha256=PROTOCOL,
        program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        entry_receipt_sha256=ENTRY, service_receipt_sha256=SERVICE,
        pr45=service["pr45_head"], distinct_demands=len(first), known_primary=1424,
        unknown_primary=16, outside_known_by_tier=dict(symbolic_only),
        distinct_cold_after_unknown_grant_by_tier=dict(by_tier),
        keys_without_measured_generation_granted_zero={
            tier: missing_prices[tier] for tier in ("CPU", "CUDA0")},
        baseline_calls=[dict(tokens=x["tokens"], jobs=x["jobs"], components=x["component_reads"],
                             read_worker_us=x["read_worker_us"]) for x in service["calls"]],
        budget_s=BUDGET_US / 1e6, by_capacity={
            str(k): dict(additional_payload_bytes=k * PAYLOAD, minimum_cold_reads=max(0, n - k),
                         minimum_read_payload_bytes=max(0, n - k) * PAYLOAD,
                         byte_floor_at_4_5_GB_s=max(0, n - k) * PAYLOAD / 4.5e9) for k in SIZES},
        byte_scenario_min_additional_entries=byte_cutoff,
        byte_scenario_cutoff_payload_bytes=byte_cutoff * PAYLOAD,
        four_worker_volume=classify(volume), strict_layer_major=classify(phase),
        forwards=0, weight_reads=0, gpu_used=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "trace", "pr45-checkout", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (384 << 20, 384 << 20))
    signal.alarm(120)
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        result = run(a.repo.resolve(), a.trace.resolve(), a.pr45_checkout.resolve())
    except FileNotFoundError as exc:
        result = {"status": "NOT_RUN_RAW_REQUIRED", "file": Path(exc.filename).name}
    except (OSError, ValueError, KeyError, MemoryError) as exc:
        result = {"status": "INCONCLUSIVE_PRESERVED", "reason": str(exc)}
    data = json.dumps(result, indent=2, allow_nan=False) + "\n"
    require(len(data.encode()) <= 2 << 20, "receipt budget")
    pending = a.new_output_dir / ".pending"
    pending.write_text(data)
    pending.rename(a.new_output_dir / "receipt.json")
    return int(result["status"] != "REPRODUCED_C135_CONDITIONAL_FLOORS")


if __name__ == "__main__":
    raise SystemExit(main())
