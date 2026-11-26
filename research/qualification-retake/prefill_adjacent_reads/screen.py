"""C135 eligible contiguous GGUF slices, requested lengths and optimistic residual floor."""

import argparse
import json
import resource
import signal
import sys
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "prefill_read_floor"))
import bound  # noqa: E402

dispatch = bound.dispatch
require = dispatch.require
INVENTORY = "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
FLOOR_HELPER = "20ef296cf4d1dd78e1a3d6341e36d1bce2c53d46c87f59b7eb7d7dcf8279bfba"
FLOOR_RECEIPT = "f2cd36d9b060e4864de620aab05013fe462b9a581b86474a3d127abd1b66c8cf"
PROTOCOL = "3898c0cf35172733e03455d9a638af065a58c858eb712963f8fbd92a9d14a458"
SIZE, ALIGN, FILE_BYTES = 4_406_400, 4096, 63_387_346_208


def sources(inventory):
    require(dispatch.digest(inventory) == INVENTORY, "GGUF inventory digest")
    tables = [json.loads(line) for line in inventory.read_text().splitlines()]
    require(tables[0]["tensor_count"] == len(tables) - 1 == 687, "incomplete GGUF inventory")
    by_name = {t["name"]: t for t in tables[1:]}
    offsets = {}
    for layer in range(36):
        offsets[layer] = []
        for name in ("gate", "down", "up"):
            t = by_name[f"blk.{layer}.ffn_{name}_exps.weight"]
            require(t["tensor_type"] == "mxfp4" and t["shape"] == [2880, 2880, 128]
                    and t["n_bytes"] == 128 * SIZE, "expert layout")
            offsets[layer].append(t["data_offset"])
    return offsets


def aligned_length(offset, logical):
    begin = offset // ALIGN * ALIGN
    end = (offset + logical + ALIGN - 1) // ALIGN * ALIGN
    require(0 <= begin < end <= FILE_BYTES, "aligned interval outside GGUF")
    return end - begin


def identify(rows, critical):
    tile, last_layer, wave = -1, 36, None
    first, dequeued, role_at = {}, {}, {}
    counts = Counter()
    for row in rows:
        kind, layer = row["kind"], row["layer"]
        logical, slot = row["expert"], row["slot"]
        key = critical.generation(row)
        if kind == "DEMAND":
            if layer < last_layer:
                tile += 1
            last_layer, wave = layer, row["wave"]
            role_at[layer, logical] = (tile, wave, "demand", slot, row["seq"])
        elif kind == "PRELOAD":
            require(layer == last_layer and row["wave"] == wave + 1, "preload origin")
            role_at[layer, logical] = (tile, wave, "preload", slot, row["seq"])
        elif kind == "ENQUEUE":
            t, w, role, announced_slot, seq = role_at[layer, logical]
            require((t, layer, w) == (tile, last_layer, wave) and seq < row["seq"]
                    and announced_slot in (-1, slot), "enqueue origin mismatch")
            if key in first:
                require(role == "demand", "duplicate preload")
                counts["repeat_enqueues"] += 1
            else:
                first[key] = (tile, layer, wave, role, row["seq"])
                counts[role] += 1
        elif kind == "DEQUEUE":
            require(key in first and key not in dequeued, "missing or repeated queue acceptance")
            dequeued[key] = row["seq"]
    require(first.keys() == dequeued.keys(), "unaccepted generations")
    return first, dequeued, counts


def adjacent_runs(keys, first, dequeued, simultaneous):
    """Partition in ascending logical ID. Split a run once its queue windows cease intersecting."""
    ordered = sorted(keys, key=lambda key: key[1])
    require(len({k[1] for k in ordered}) == len(ordered), "repeated ID in one scope")
    runs = []
    for _, group in groupby(enumerate(ordered), key=lambda item: item[1][1] - item[0]):
        run = []
        for _, key in group:
            if run and simultaneous:
                combined = run + [key]
                if max(first[k][-1] for k in combined) >= min(dequeued[k] for k in combined):
                    runs.append(run)
                    run = []
            run.append(key)
        runs.append(run)
    return runs


def counter(runs, offsets):
    original = combined = participants = 0
    merged, lengths = set(), Counter()
    for run in runs:
        layer = run[0][0]
        offsets3 = offsets[layer]
        require(all(k[0] == layer for k in run), "cross-layer range")
        lengths[len(run)] += 1
        if len(run) > 1:
            participants += len(run)
            merged.update(run)
        for base in offsets3:
            original += sum(aligned_length(base + k[1] * SIZE, SIZE) for k in run)
            combined += aligned_length(base + run[0][1] * SIZE, len(run) * SIZE)
    n = sum(len(r) for r in runs)
    return merged, dict(
        generations=n, contiguous_groups_by_size=dict(sorted(lengths.items())),
        potential_participants=participants, preads_before=n * 3, preads_after=len(runs) * 3,
        original_logical_bytes=n * 3 * SIZE, original_aligned_requested_bytes=original,
        grouped_aligned_requested_bytes=combined,
        grouped_participant_payload_bytes=participants * 3 * SIZE,
    )


def evaluate(rows, offsets, critical, baseline):
    require(bound.floor(rows, critical) == baseline, "C135 mandatory READ floor differs")
    first, dequeued, counts = identify(rows, critical)
    scopes = (bound.small_call(rows, critical) if baseline["tokens"] == 5
              else dispatch.build_scopes(rows, critical)[0])
    witnessed, relaxed = [], []
    by_service = {}
    for number, scope in enumerate(scopes):
        by_role = defaultdict(list)
        keys = [k for k, *_ in scope["jobs"]]
        require(len({first[k][:2] for k in keys}) == 1, "ambiguous consumer vs enqueue scope")
        for k, _, _, _, parts in scope["jobs"]:
            by_role[first[k][2:4]].append(k)
            by_service[k] = number, max(0, parts["read"] - 3)
        for group in by_role.values():
            witnessed.extend(adjacent_runs(group, first, dequeued, True))
        relaxed.extend(adjacent_runs(keys, first, dequeued, False))
    actual, a = counter(witnessed, offsets)
    free, b = counter(relaxed, offsets)
    require(actual <= free and set(by_service) == set(first) and len(first) == baseline["jobs"],
            "participants/call conservation")
    fixed = defaultdict(list)
    for key in set(first) - free:
        number, duration = by_service[key]
        fixed[number].append(duration)
    floor_fourths = sum(max(sum(durations), 4 * max(durations)) for durations in fixed.values())
    return dict(tokens=baseline["tokens"], producers=dict(counts), witnessed=a,
                relaxed=b, unconditional_in_scope_isolated_jobs=len(first) - len(free),
                residual_fixed_read_floor_us=floor_fourths / 4)


def run(trace, checkout, inventory):
    require(dispatch.digest(Path(bound.__file__)) == FLOOR_HELPER, "changed read-floor code")
    require(dispatch.digest(Path(dispatch.__file__)) == bound.SOURCE, "changed dispatch")
    require(dispatch.digest(HERE / "protocol.md") == PROTOCOL, "changed protocol")
    ref = HERE.parent / "prefill_read_floor/replay-r2/receipt.json"
    require(dispatch.digest(ref) == FLOOR_RECEIPT, "changed baseline receipt")
    base = json.loads(ref.read_text())
    require(trace.stat().st_size == 3603647 and dispatch.digest(trace) == dispatch.TRACE, "C135")
    history = HERE.parents[2] / "results/c135-slots40-warm153-trace-20260929T2205Z/analysis.json"
    require(dispatch.digest(history) == bound.ANALYSIS, "C135 timings")
    offsets = sources(inventory)
    critical, _ = dispatch.imports(checkout)
    critical.validate(trace)
    _, rows = critical.trace_rows(trace)
    arms = [evaluate([r for r in rows if r["call_id"] == call], offsets, critical, expected)
            for call, expected in enumerate(base["calls"], 1)]
    floor = sum(arm["residual_fixed_read_floor_us"] for arm in arms)
    return dict(classification="TRACE_DERIVED_CONDITIONAL_HEADROOM", protocol_sha256=PROTOCOL,
                raw_sha256=dispatch.TRACE, inventory_sha256=INVENTORY, prior_sha256=FLOOR_RECEIPT,
                arms=arms, residual_floor_us=floor, ceiling_budget_us=2427104.435,
                decision="NO_GO_FIXED_SERVICE_C135_10S_AT_SIX" if floor > 2427104.435
                else "INCONCLUSIVE_PHYSICAL_SERVICE")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--pr45-checkout", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    args = p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    signal.alarm(60)
    require(not args.new_output_dir.resolve().is_relative_to(args.trace.resolve().parent)
            and not args.new_output_dir.resolve().is_relative_to(args.inventory.resolve().parent),
            "protect source raw")
    args.new_output_dir.mkdir(parents=True, exist_ok=False)
    report = run(args.trace, args.pr45_checkout, args.inventory)
    pending = args.new_output_dir / "receipt.pending"
    pending.write_text(json.dumps(report, indent=2) + "\n")
    pending.replace(args.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
