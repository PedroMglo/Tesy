"""Locate historical prefill readmissions by external call and numerical tile."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from audit import ROOT, require, source

sys.path.insert(0, str(ROOT / "tools"))
from c2_gate import GateError  # noqa: E402
from c122_trace_validate import validate  # noqa: E402
from c123_analyze_trace import sha, trace_rows  # noqa: E402

C261 = "results/c261-slots40-prefill-opportunity-20261004/analysis.json"
PLAN = {1: (5,), 2: (32, 32, 32, 32, 20)}
CLASSES = ("first_in_phase", "between_calls", "between_tiles_same_call", "within_tile")


def group_prefill(rows):
    last_tile_by_expert, enqueues, counts, decode_probe = {}, {}, Counter(), Counter()
    observed_tiles = {call: [] for call in PLAN}
    tile, previous = -1, -1
    for e in rows:
        call, kind, layer, expert, slot, gen, positions = (
            e[k] for k in ("call_id", "kind", "layer", "expert", "slot", "generation", "n_tokens")
        )
        if call not in (1, 2, 3):
            break
        logical = layer, expert
        tier = "CPU" if layer < 25 else "CUDA0"
        if call == 3:
            if kind == "DEMAND" and e["state"] == 2:
                origin = last_tile_by_expert.get(logical)
                decode_probe[tier, "hits"] += 1
                decode_probe[tier, "hits_seen_in_prefill"] += origin is not None
            elif kind == "LOAD_BEGIN":
                decode_probe[tier, "loads"] += 1
            continue
        if kind == "CALL_BEGIN":
            tile, previous = -1, 36
        if kind == "DEMAND":
            # The numerical graph traverses layers in order, potentially pruning
            # the last FFN on tiles with no requested rows. A decrease to layer
            # zero can only enter the next graph within the current call.
            if layer < previous:
                require(layer == 0 and e["wave"] in (-1, 0), "ambiguous tile boundary")
                tile += 1
                observed_tiles[call].append(positions)
            expected = PLAN[call][tile]
            require(positions == expected or (call == 2 and layer == 35 and positions == 1),
                    "unexpected width in tile")
            previous = layer
            if e["state"] == 2:
                last_tile_by_expert[logical] = (call, tile)
        elif kind == "ENQUEUE":
            key = call, layer, expert, slot, gen
            require(layer >= previous,
                    "unexpected enqueue from an earlier layer")
            enqueues.setdefault(key, tile)
        elif kind == "LOAD_BEGIN":
            key = call, layer, expert, slot, gen
            load_tile = enqueues[key]
            require(load_tile == tile, "load crosses a numerical tile boundary")
            prev = last_tile_by_expert.get(logical)
            if prev is None:
                category = "first_in_phase"
            elif prev[0] != call:
                category = "between_calls"
            elif prev[1] != tile:
                category = "between_tiles_same_call"
            else:
                category = "within_tile"
            counts[tier, category] += 1
            last_tile_by_expert[logical] = (call, tile)
    require({call: tuple(widths) for call, widths in observed_tiles.items()} == PLAN,
            "call or tile plan changed")
    return counts, decode_probe


def report(path):
    frozen = source.archived(C261)
    require(sha(path) == frozen["trace_sha256"], "C135 trace SHA-256 mismatch")
    validated = validate(path)
    require(set(validated["calls"]) == set(range(1, 49)), "C135 call inventory changed")
    layers, rows = trace_rows(path)
    require(all(info["device"] == ("CPU" if layer < 25 else "CUDA0")
                and info["bytes"] == 13_219_200 for layer, info in layers.items()),
            "placement or original byte size changed")
    counts, first_decode = group_prefill(rows)
    report = {}
    for tier in ("CPU", "CUDA0"):
        recorded = frozen["tiers"][tier]
        breakdown = {key: counts[tier, key] for key in CLASSES}
        require(sum(breakdown.values()) == recorded["actual_loads"]
                and sum(breakdown[key] for key in CLASSES[1:])
                == recorded["repeated_after_observed_ready_or_load"], "C261 totals differ")
        report[tier] = {
            "load_partition": breakdown,
            "logical_bytes_of_cross_tile_candidates": breakdown["between_tiles_same_call"]
            * 13_219_200,
            "first_decode": {k: first_decode[tier, k]
                             for k in ("hits", "hits_seen_in_prefill", "loads")},
        }
    return {"c135_trace_sha256": frozen["trace_sha256"], "numerical_tile_plan": PLAN,
            "classification": "HISTORICAL_TRACE_DIAGNOSTIC", "tiers": report}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--trace", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    with args.output.open("x", encoding="utf-8") as out:
        try:
            result = report(args.trace)
        except (ValueError, KeyError, OSError, GateError) as exc:
            print(json.dumps({"decision": "INCONCLUSIVE", "failure": str(exc)}), file=out)
            sys.exit(1)
        print(json.dumps(result, indent=2), file=out)
