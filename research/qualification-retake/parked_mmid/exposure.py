"""Count empty CPU waves by tile in the authenticated C135 nominal increment."""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from itertools import groupby
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORACLE = HERE.parent / "prefill_oracle40/screen.py"
WIDTHS = (32, 32, 32, 32, 20)


def count(trace):
    spec = importlib.util.spec_from_file_location("c135_oracle", ORACLE)
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    digest = hashlib.sha256(trace.read_bytes()).hexdigest()
    oracle.require(trace.stat().st_size == 3603647 and digest == oracle.TRACE, "C135 identity")
    oracle.validate(trace)
    layers, rows = oracle.trace_rows(trace)
    prompt = [r for r in rows if r["call_id"] == 2]
    oracle.demands_by_layer(prompt, WIDTHS, final_output=True)
    demands = (r for r in prompt if r["kind"] == "DEMAND")
    groups = iter(groupby(demands, key=lambda r: r["layer"]))
    tiles = []
    for i, width in enumerate(WIDTHS):
        histogram = Counter()
        n_waves = (min(128, 4 * width) + 17) // 18
        for expected in range(36 if i == 4 else 35):
            layer, records = next(groups)
            active = len({r["wave"] for r in records})
            oracle.require(layer == expected, "tile sequence")
            if layers[layer]["device"] == "CPU":
                oracle.require(1 <= active <= n_waves, "active waves")
                histogram[active] += 1
        oracle.require(sum(histogram.values()) == 25, "CPU layer coverage")
        empty = sum((n_waves - active) * qty for active, qty in histogram.items())
        tiles.append(dict(tile=i, width=width, waves_per_layer=n_waves, empty=empty,
                          layers_by_active_waves=dict(sorted(histogram.items()))))
    oracle.require(next(groups, None) is None and sum(t["empty"] for t in tiles) == 737,
                   "demand conservation")
    # Gate/up each convert one row per token. Down converts four. All have K=2880.
    converted = sum(6 * 2880 * t["width"] * t["empty"] for t in tiles)
    return dict(status="TRACE_DERIVED", trace_sha256=digest, tiles=tiles,
                eligible_mmid_calls=3 * 737, f32_elements_eligible=converted,
                f32_input_logical_bytes=converted * 4,
                q8_0_output_logical_bytes=converted // 32 * 34)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(count(args.trace), indent=2))
