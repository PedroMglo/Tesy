"""Optimistic whole-prefill cache misses for the two C135 calls in one conversation."""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from itertools import groupby
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "tools"))
import cache_bound  # noqa: E402
from c122_trace_validate import validate  # noqa: E402
from c123_analyze_trace import trace_rows  # noqa: E402

CACHE = 40
PAYLOAD = 13_219_200
RATE = 4_500_000_000
PIN = "ba058e62c33f6e1c6d8581c4685d9abb64542027"
PIN45 = "83146dade3f90235775e4a31a8d3d8ccae3476a7"
TRACE = "91610b12291d5a42a12bba09f5d4ff188d25ee0001ab89e894bdd508005e82fb"
ANALYSIS = "results/c135-slots40-warm153-trace-20260929T2205Z/analysis.json"
HASHES = {
    ANALYSIS: "2a331bafe266decf08112fe5166c6801738fdb6666a3cfe0e26d59f2346bc056",
    "research/qualification-retake/cache_bound.py": "7a1eca13746bac6a2f0b2a989040374e801d0e058d58240d022b80ddb07b4e46",  # noqa: E501
    "tools/c122_trace_validate.py": "7de57a93f3ac9eb60ae2ae7bc4e1a712b695a4f4ae56fb5e21ce546d3ffb441c",  # noqa: E501
    "tools/c123_analyze_trace.py": "f68f8f5126a33d0286355a664ccfb14292e1f4679a55629b06175fa8b26646ce",  # noqa: E501
}
SOURCE_SHA = "b7ca5f9608f4c20140a51748f88ff64657c0d586f0edc527d4cabd5fd39f2d4c"
GRAPH_SHA = "eab00ef87d7212708f3ac4ec4f643dfc1c640f9949633827ff5017e7c56c705c"
MODEL_GRAPH_SHA = "239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4"
SERVER_SHA = "657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55"
CERT45 = "8bac276e0b9a0e65c7b6e7c54bc6680f88774fdd77431a2d614939c17cabdc57"


def require(condition, label):
    if not condition:
        raise ValueError(label)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def demands_by_layer(rows, widths, *, final_output):
    """Each wave emits its first-use union before testing for resident hits."""
    demand = [r for r in rows if r["kind"] == "DEMAND"]
    runs = [(layer, list(records)) for layer, records in groupby(demand, key=lambda r: r["layer"])]
    expected = [
        (tile, layer)
        for tile in range(len(widths))
        for layer in range(36 if final_output and tile == len(widths) - 1 else 35)
    ]
    require([layer for layer, _ in runs] == [layer for _, layer in expected], "layer/tile coverage")
    groups = [[] for _ in range(36)]
    for (tile, layer), (_, records) in zip(expected, runs, strict=True):
        width = 1 if layer == 35 else widths[tile]
        require(all(r["n_tokens"] == width for r in records), "effective FFN rows")
        ids = [r["expert"] for r in records]
        require(len(set(ids)) == len(ids) and all(0 <= e < 128 for e in ids), "expert identity")
        require(4 <= len(ids) <= 4 * width, "distinct top-4 coverage")
        waves = [
            (w, tuple(r["expert"] for r in rs))
            for w, rs in groupby(records, key=lambda r: r["wave"])
        ]
        require((waves[0][0] == -1) == (4 * width <= CACHE), "graph wave mode")
        if waves[0][0] == -1:
            require(len(waves) == 1 and len(ids) <= CACHE, "single-wave remap")
        else:
            require([w for w, _ in waves] == list(range(len(waves))), "nonempty wave sequence")
            require(
                all(len(es) == 18 for _, es in waves[:-1]) and len(waves[-1][1]) <= 18,
                "wave capacity",
            )
        groups[layer].extend(es for _, es in waves)
    return groups


def solve(first, second, capacity=CACHE):
    """One layer with one initial warm grant. No extra grant at the call return."""
    require(len(first) <= 1, "first call has at most one pin group per layer")
    all_groups = first + second
    unique = set().union(*all_groups)
    distinct_floor = max(0, len(unique) - capacity)
    joint = cache_bound.minimum(all_groups, capacity)
    # This is the same earliest-first-use start used by the joint solver.
    # All of the only pin group in call 1 can be present for free.
    require(all(len(group) <= capacity for group in first), "first call pins")
    require(cache_bound.minimum(first, capacity) == 0 and joint >= distinct_floor, "joint floor")
    return {
        "distinct": len(unique),
        "distinct_floor": distinct_floor,
        "optimal_call5": 0,
        "optimal_call148": joint,
        "optimal_total": joint,
        "call5_waves": len(first),
        "call148_waves": len(second),
        "call5_distinct": len(set().union(*first)),
        "call148_distinct": len(set().union(*second)),
    }


def decision(loads, budget):
    limit = budget * RATE // PAYLOAD
    floor = Fraction(loads * PAYLOAD, RATE)
    require(limit == 826, "unexpected C135 threshold")
    return {
        "comparison": "NO_GO_NOMINAL_RATE_AND_FIXED_GEOMETRY"
        if loads > limit
        else "INCONCLUSIVE_CAUSAL_POLICY_AND_COST_REQUIRED",
        "c135_budget_s": float(budget),
        "budget_s_fraction": str(budget),
        "assumed_decimal_bytes_s": RATE,
        "max_loads": limit,
        "read_floor_s_at_nominal_rate": float(floor),
        "remaining_budget_s": float(budget - floor),
        "required_bytes_s": float(loads * PAYLOAD / budget),
        "min_loads_to_remove_from_observed": 1222 - limit,
        "headroom_loads": limit - loads,
    }


def commit(checkout):
    return subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()


def run(trace, backend, pr45):
    if not trace.is_file():
        return {
            "status": "NOT_RUN_RAW_REQUIRED",
            "required_trace_sha256": TRACE,
            "required_size": 3603647,
        }
    require(trace.stat().st_size == 3603647 and sha(trace) == TRACE, "C135 raw identity")
    for name, expected in HASHES.items():
        require(sha(ROOT / name) == expected, name)
    source = backend / "src/llama-moe-stream.cpp"
    require(sha(backend / "src/llama-graph.cpp") == GRAPH_SHA, "C122 graph wave condition")
    require(
        sha(backend / "src/models/openai-moe.cpp") == MODEL_GRAPH_SHA,
        "C122 FFN output row selection",
    )
    require(sha(backend / "tools/server/server-context.cpp") == SERVER_SHA, "C122 prompt outputs")
    prior = pr45 / "research/prefill-slot-proof/victim-evidence/receipt.json"
    require(commit(backend) == PIN and sha(source) == SOURCE_SHA, "C122 DEMAND emitter")
    require(commit(pr45) == PIN45 and sha(prior) == CERT45, "PR45 receipt")
    reload_evidence = pr45 / "research/prefill-slot-proof/evidence/receipt.json"
    reload_sha = "74335e5f97ced6a82c3204ccea3a7e0828e4a231ac314a34c5b778ce0dfaff84"
    require(sha(reload_evidence) == reload_sha, "PR45 cross-tile receipt")
    reloads = json.loads(reload_evidence.read_text())
    require(
        reloads["c135_sha256"] == TRACE
        and reloads["selection"]["candidate_partition"]["candidates"] == 184,
        "cross-tile count",
    )
    known = json.loads(prior.read_text())
    require(known["trace_sha256"] == TRACE, "PR45 arm")
    validate(trace)
    layers, all_rows = trace_rows(trace)
    parts = [[r for r in all_rows if r["call_id"] == c] for c in (1, 2)]
    require(len(all_rows) == 58181, "journal length")
    by_call = []
    actual = []
    # The server requests output only on the last prompt token (position 2196).
    calls = (([5], 2044, 2048, False), ([32, 32, 32, 32, 20], 2049, 2196, True))
    for rows, (widths, start, end, output) in zip(parts, calls, strict=True):
        require(
            all((r["expert"], r["slot"]) == (start, end) for r in (rows[0], rows[-1])),
            "C135 prompt positions",
        )
        require(
            rows[0]["kind"] == "CALL_BEGIN"
            and rows[-1]["kind"] == "CALL_END"
            and rows[0]["n_tokens"] == sum(widths),
            "external prefill call",
        )
        by_call.append(demands_by_layer(rows, widths, final_output=output))
        actual.append(Counter(r["layer"] for r in rows if r["kind"] == "LOAD_BEGIN"))
    require([sum(counts.values()) for counts in actual] == [45, 1177], "historical loads")
    per_layer = []
    for layer in range(36):
        device = "CPU" if layer < 25 else "CUDA0"
        require(layers[layer] == {"device": device, "bytes": PAYLOAD}, "metadata")
        result = solve(by_call[0][layer], by_call[1][layer])
        reference = known["by_layer"][layer]
        require(
            reference["layer"] == layer
            and result["call148_distinct"] == reference["distinct_demands"]
            and actual[1][layer] == reference["historical_loads"],
            "PR45 layer cross-check",
        )
        per_layer.append(
            {
                "layer": layer,
                "tier": device,
                **result,
                "historical_call5": actual[0][layer],
                "historical_call148": actual[1][layer],
            }
        )
    totals = {}
    for tier in ("CPU", "CUDA0", "all"):
        rows = [layer for layer in per_layer if tier in (layer["tier"], "all")]
        totals[tier] = {
            k: sum(layer[k] for layer in rows) for k in rows[0] if k not in ("layer", "tier")
        }
    best = totals["all"]["optimal_total"]
    require(best <= 1222, "oracle worse than observed feasible policy")
    times = json.loads((ROOT / ANALYSIS).read_text(), parse_float=Decimal)["server"]["trace_on"]
    require(times["warm_output_tokens"] == 47, "natural output count")
    budget = (
        10
        - Fraction(times["warm_first_final_s"])
        + Fraction(times["warm_prefill_s"])
        + Fraction(times["warm_decode_s"])
        - Fraction(47, 6)
    )
    facts = {
        "observed": 1222,
        "only_cross_tile_reloads_removed": 1222 - 184,
        "relaxed_misses": best,
        "max_reads_saved_vs_observed": 1222 - best,
        "payload_bytes": best * PAYLOAD,
    }
    return {
        "status": "PASS_TRACE_DERIVED_OFFLINE_BOUND",
        "trace_sha256": TRACE,
        "protocol_sha256": sha(HERE / "protocol.md"),
        "program_sha256": sha(Path(__file__)),
        "backend_pin": PIN,
        "emitter_sha256": SOURCE_SHA,
        "graph_sha256": GRAPH_SHA,
        "model_graph_sha256": MODEL_GRAPH_SHA,
        "server_source_sha256": SERVER_SHA,
        "ffn35_output_rows_by_call_and_tile": [[0], [0, 0, 0, 0, 1]],
        "pr45_pin": PIN45,
        "pr45_receipt_sha256": CERT45,
        "pr45_cross_tile_receipt_sha256": reload_sha,
        "inputs": HASHES,
        "source_calls": [5, 148],
        "tier_totals": totals,
        "load_comparison": facts,
        "time_scenario": decision(best, budget),
        "layers": per_layer,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--pr45-checkout", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.new_output_dir.resolve()
    require(not out.is_relative_to(args.trace.resolve().parent), "protect raw trace")
    out.mkdir(exist_ok=False)
    try:
        report = run(args.trace, args.backend, args.pr45_checkout)
    except Exception as exc:
        (out / "failure.json").write_text(json.dumps({"status": "FAIL", "reason": str(exc)}) + "\n")
        raise
    tmp = out / "receipt.pending"
    tmp.write_text(json.dumps(report, indent=2) + "\n")
    tmp.replace(out / "receipt.json")
    print(report["status"], report.get("time_scenario", {}).get("comparison", ""))
