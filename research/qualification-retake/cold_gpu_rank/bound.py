"""Conditional floors on the original 32 supplied decode steps. No model file access."""

import argparse
import hashlib
import json
import resource
import signal
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE.parent))
from c122_trace_validate import union_us  # noqa: E402
from cache_boundary import CAMPAIGN, HEADER, MANIFEST, MANIFEST_SHA, NAMES, require  # noqa: E402

COMPACT_SHA = "bc89290458407007f755c341fcbb3fd7c1fd8bdd82cfc4b1a71d1bd8249000c1"
PROTOCOL_SHA = "5213ef377ebc958706da9e0d42b54ddb02eb0ec38e8c7d0726fd775b9979592d"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def events(path):
    with path.open() as stream:
        require(next(stream).strip() == HEADER, "event schema")
        columns = HEADER.split()
        for line in stream:
            yield dict(zip(columns, map(int, line.split()), strict=True))


def minimum_duration(begin, end):
    require(end >= begin, "negative observed duration")
    return max(0, end - begin - 1)  # endpoints truncated to microseconds


def arm(rows, native_decode_s):
    steps = defaultdict(list)
    for row in rows:
        steps[row["call"]].append(row)
    previous = max(row["us"] for row in steps[0] if row["kind"] == 16)
    require(all(row["us"] <= previous for row in steps[0] if row["layer"] >= 25),
            "GPU service crosses the prefill return")
    gross_floor = first_read_floor = fixed_read_floor = active_layers = generations = 0
    launch_floor = journal_calls = 0
    set_intervals = []
    for call in range(1, 33):
        batch = steps[call]
        begin, end = [next(x["us"] for x in batch if x["kind"] == k) for k in (15, 16)]
        feature = next(x["us"] for x in batch if x["kind"] == 1 and x["layer"] == 24)
        require(previous <= begin <= feature <= end, "overlapping calls or misplaced CPU24")
        previous = end
        journal_calls += end - begin
        gross_floor += minimum_duration(begin, feature)
        last_gate = end
        first_eligible_router = None
        first_copy_opportunity = end
        longest_reads = 0
        for layer in range(35, 24, -1):
            group = [x for x in batch if x["layer"] == layer]
            router = next(x for x in group if x["kind"] == 2)
            route_time = router["us"]
            require(feature <= route_time <= last_gate, "broken layer order")
            missing = {x["expert"] for x in group if x["kind"] == 3 and x["bytes"] != 2}
            jobs = [x for x in group if x["kind"] == 5]
            require(len(jobs) == len(missing) and {x["expert"] for x in jobs} == missing,
                    "absent/loading ranks differ from this layer's physical generations")
            if jobs:
                first_eligible_router = route_time
                active_layers += 1
            spans = []
            for job in jobs:
                require(job["route"] == router["route"], "load began outside authoritative route")
                key = (job["expert"], job["slot"], job["gen"], job["route"])
                phases = {(x["component"], x["kind"]): x["us"] for x in group
                          if (x["expert"], x["slot"], x["gen"], x["route"]) == key}
                require(route_time <= job["us"] <= phases[-1, 10] <= last_gate,
                        "service extends outside serial layer window")
                first_copy_opportunity = min(first_copy_opportunity, phases[0, 7])
                spans.append(sum(minimum_duration(phases[k, 6], phases[k, 7]) for k in range(3)))
                set_intervals.extend((phases[k, 8], phases[k, 9]) for k in range(3))
            generations += len(jobs)
            longest_reads += max(spans, default=0)
            last_gate = route_time
        first_read_floor += minimum_duration(begin, first_copy_opportunity)
        if first_eligible_router is None:
            fixed_read_floor += minimum_duration(begin, end)
        else:
            launch_floor += minimum_duration(begin, first_eligible_router)
            fixed_read_floor += minimum_duration(begin, first_eligible_router) + longest_reads

    best = max(first_read_floor, fixed_read_floor)
    require(best <= journal_calls and journal_calls / 1e6 <= native_decode_s + 32e-6,
            "call spans exceed enclosing native decode clock")
    return {
        "decode32_s": native_decode_s, "journal_calls_us": journal_calls,
        "cpu24_floor_us": gross_floor, "first_read_floor_us": first_read_floor,
        "fixed_read_floor_us": fixed_read_floor, "eligible_router_prefixes_us": launch_floor,
        "conditional_saving_upper_s": native_decode_s - best / 1e6,
        "conditional_tps_upper": 32e6 / best, "excludes_six": best * 6 > 32_000_000,
        "gpu_layer_calls_with_miss": active_layers, "gpu_generations": generations,
        "gpu_component_sets": len(set_intervals), "gpu_set_union_us": union_us(set_intervals),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    signal.alarm(60)
    require(not args.new_output_dir.resolve().is_relative_to(args.raw_dir.resolve()),
            "raw protected")
    require(sha(HERE / "protocol.md") == PROTOCOL_SHA, "changed protocol")
    require(sha(MANIFEST) == MANIFEST_SHA, "changed manifest")
    compact_path = MANIFEST.with_name("compact.json")
    require(sha(compact_path) == COMPACT_SHA, "changed arm registry")
    args.new_output_dir.mkdir(parents=True, exist_ok=False)
    compact = json.loads(compact_path.read_text())
    registry = {x["id"]: x for x in compact["arms"]}
    manifest = {x["path"]: x for x in json.loads(MANIFEST.read_text())["files"]}
    out = {}
    for name in NAMES:
        relative = f"{name}.native/events.tsv"
        path = args.raw_dir / relative
        expected = manifest[f"results/{CAMPAIGN}/raw/{relative}"]
        require(path.stat().st_size == expected["bytes"] and sha(path) == expected["sha256"],
                "raw identity")
        entry = registry[name]
        require(entry["trace"] and entry["measurement_valid"], "unqualified trace")
        out[name] = dict(events_sha256=expected["sha256"],
                         **arm(events(path), entry["timings"]["decode32_s"]))
    report = dict(protocol_sha256=PROTOCOL_SHA, raw_manifest_sha256=MANIFEST_SHA,
                  arm_registry_sha256=COMPACT_SHA, arms=out)
    pending = args.new_output_dir / "receipt.pending"
    pending.write_text(json.dumps(report, indent=2) + "\n")
    pending.replace(args.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
