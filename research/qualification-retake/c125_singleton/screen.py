"""Recover the registered C125B ABBA contrast for single-miss groups."""

import argparse
import hashlib
import json
import math
import resource
import signal
import sys
from pathlib import Path
from statistics import median

CAMPAIGN = "c125b-component-io-probe-20260929T1555Z"
PROTOCOL = "261972fbef15f80335edf53cd2695b110f23ec10278ce455dc9ec64907297756"
C125 = {
    "protocol.json": "4e94c8faf098b90ac50167216ae4c7dcab6e4ba1499148110c60405aec51f271",
    "manifest.json": "d433db8d34f0f9883024ccc58e0991f1df8e368a31de77cb21a1cb77706b159d",
    "decision.json": "0d4f5a45d3db68d80466d08365b05c8a22dc2db9fa7b037b1620f77f3868ecc2",
}
SOURCES = {
    "c125_component_io_probe.py": "2e7a2187e6db1d8b45d9049fc947d6de3850cddec51cb239a2f91dfdfa15042e",  # noqa: E501
    "c122_trace_validate.py": "7de57a93f3ac9eb60ae2ae7bc4e1a712b695a4f4ae56fb5e21ce546d3ffb441c",
    "c123_analyze_trace.py": "f68f8f5126a33d0286355a664ccfb14292e1f4679a55629b06175fa8b26646ce",
}
SOURCE_COMMIT = "4b9b650ff6ba4f809e74fad4b48aa244fb782057"
MEASURE = "27e46fa5c5e01be6b154ff3de4a4792942fc5e5c"
ORDER = ("serial", "parallel", "parallel", "serial")
PAIRS = ((0, 1), (3, 2))
SLAB = 4_406_400


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned(path, digest, size=None):
    data = path.read_bytes()
    require(size is None or len(data) == size, "size " + path.name)
    require(hashlib.sha256(data).hexdigest() == digest, "digest " + path.name)
    return data


def series(cardinalities, rows):
    """Use exactly the four sealed vectors against the one authenticated schedule."""
    require(len(rows) == 4 and cardinalities, "four arms on a nonempty schedule")
    require(all(type(n) is int and 1 <= n <= 4 for n in cardinalities), "group cardinality")
    for vector in rows:
        require(len(vector) == len(cardinalities), "group alignment")
        require(all(type(t) in (float, int) and math.isfinite(t) and t > 0 for t in vector),
                "invalid group duration")
    result = {}
    for key in ["all", *sorted(set(cardinalities))]:
        indices = [i for i, n in enumerate(cardinalities) if key == "all" or n == key]
        n = len(indices)
        sums = [math.fsum(vector[i] for i in indices) for vector in rows]
        pairs = []
        for a, b in PAIRS:
            t0 = sums[a]
            t1 = sums[b]
            pairs.append({
                "T0_arm": a + 1, "T1_arm": b + 1, "T0_s": t0, "T1_s": t1,
                "T0_mean_ms": 1000 * t0 / n, "T1_mean_ms": 1000 * t1 / n,
                "mean_paired_difference_ms": 1000 * (t0 - t1) / n,
                "T1_over_T0": t1 / t0, "gain_percent": 100 * (1 - t1 / t0),
                "positive_groups": sum(rows[b][i] < rows[a][i] for i in indices),
                "tied_groups": sum(rows[b][i] == rows[a][i] for i in indices),
            })
        gains = [p["gain_percent"] for p in pairs]
        jobs = sum(cardinalities[i] for i in indices)
        result[str(key)] = dict(groups=n, jobs=jobs, logical_bytes=jobs * 3 * SLAB,
                                pairs=pairs, median_gain_percent=median(gains),
                                any_positive=any(g > 0 for g in gains),
                                both_positive=all(g > 0 for g in gains))
    require("1" in result, "singleton stratum absent")
    return result


def run(repo, historical):
    pinned(Path(__file__).with_name("protocol.md"), PROTOCOL)
    tools = repo / "tools"
    for name, digest in SOURCES.items():
        pinned(tools / name, digest)
    sys.path.insert(0, str(tools))
    import c125_component_io_probe as probe

    require(Path(probe.__file__).resolve() == (tools / "c125_component_io_probe.py").resolve(),
            "unexpected source")
    path = repo / "results" / CAMPAIGN
    meta = {k: json.loads(pinned(path / k, h)) for k, h in C125.items()}
    old, manifest, dec = (meta[k] for k in C125)
    require(old["source_commit"] == SOURCE_COMMIT and dec["measurement_commit"] == MEASURE
            and tuple(old["order"]) == tuple(dec["order"]) == ORDER
            and old["direct_io"] is True and dec["read_errors"] == dec["resource_stops"] == 0,
            "native control provenance")
    require(old["trace_sha256"] == probe.EXPECTED_TRACE_SHA
            and old["gguf_inventory_sha256"] == probe.INVENTORY_SHA,
            "trace/inventory digest contract")
    probe.TRACE = historical / probe.TRACE.relative_to(probe.REPO / "results")
    probe.INVENTORY = historical / probe.INVENTORY.relative_to(probe.REPO / "results")

    workload, logical_bytes = probe.groups()
    require(probe.digest(workload) == old["group_digest"], "frozen group mapping")
    cards = [len(group) for group in workload]
    require(len(cards) == old["group_count"] == 1012 and sum(cards) == old["load_count"] == 1509
            and logical_bytes == old["logical_bytes_per_arm"] == 19_947_772_800,
            "frozen group population")
    names = [f"raw/arm{i}-{mode}.json" for i, mode in enumerate(ORDER, 1)]
    require(set(names) == set(manifest["files"]), "arm filenames")
    vectors, elapsed, raw_sha = [], [], {}
    for i, (name, mode) in enumerate(zip(names, ORDER, strict=True), 1):
        item = manifest["files"][name]
        arm = json.loads(pinned(historical / CAMPAIGN / name, item["sha256"], item["bytes"]))
        require(arm["status"] == "PASS_MODEL_FREE_IO" and arm["arm_index"] == i
                and arm["mode"] == mode and arm["measurement_commit"] == MEASURE
                and arm["protocol_sha256"] == C125["protocol.json"] and not arm["monitor_errors"]
                and arm["groups"] == len(cards) and arm["logical_bytes"] == logical_bytes
                and arm["elapsed_s"] == dec["elapsed_s"][i - 1],
                "arm provenance or conservation")
        vectors.append(arm["group_duration_s"])
        elapsed.append(arm["elapsed_s"])
        raw_sha[name] = item["sha256"]
    groups = series(cards, vectors)
    for a, b in PAIRS:
        gain = 100 * (1 - elapsed[b] / elapsed[a])
        require(math.isclose(gain, dec["paired_gain_percent"][0 if a == 0 else 1], abs_tol=1e-9),
                "whole-arm historical gain")
    require(math.isclose(median(dec["paired_gain_percent"]), dec["median_paired_gain_percent"],
                         abs_tol=1e-9), "whole-arm median")
    count = groups["1"]
    overhead = [t - math.fsum(v) for t, v in zip(elapsed, vectors, strict=True)]
    require(min(overhead) >= 0, "group sum exceeds arm")
    return {
        "status": ("GO_FIXED_FOUR_FIXTURE_ONLY" if count["both_positive"]
                   and count["median_gain_percent"] >= 15 else "NO_GO_SINGLETON_C125B"),
        "measurement_commit": MEASURE, "protocol_sha256": PROTOCOL,
        "program_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_and_reference_sha256": {**C125, **SOURCES}, "raw_sha256": raw_sha,
        "schedule_sha256": old["group_digest"], "trace_sha256": old["trace_sha256"],
        "inventory_sha256": old["gguf_inventory_sha256"], "groups_by_jobs": groups,
        "native_elapsed_s": elapsed, "outside_groups_s": overhead,
        "native_elapsed_paired_gain_percent": dec["paired_gain_percent"],
        "native_elapsed_median_gain_percent": dec["median_paired_gain_percent"],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "historical-results", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (384 << 20, 384 << 20))
    signal.alarm(60)
    out = a.new_output_dir.resolve()
    require(not out.is_relative_to(a.historical_results.resolve()), "output inside historical root")
    out.mkdir(mode=0o700, exist_ok=False)
    try:
        doc = run(a.repo.resolve(), a.historical_results.resolve())
    except FileNotFoundError as exc:
        doc = {"status": "NOT_RUN_RAW_REQUIRED", "file": Path(exc.filename).name}
    except (ValueError, AssertionError, KeyError, OSError) as exc:
        doc = {"status": "INCONCLUSIVE", "error": str(exc)}
    body = json.dumps(doc, indent=2, allow_nan=False) + "\n"
    require(len(body.encode()) < 1 << 20, "receipt too large")
    pending = out / ".pending"
    pending.write_text(body)
    pending.rename(out / "receipt.json")
    return int(doc["status"] not in ("GO_FIXED_FOUR_FIXTURE_ONLY", "NO_GO_SINGLETON_C125B"))


if __name__ == "__main__":
    raise SystemExit(main())
