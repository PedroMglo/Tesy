"""Reproduce C289 CPU SET accounting from byte-identical copies of its four raw service receipts."""

import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESULTS = ROOT / "results/c289-lossless-service-resource-qualified-20261006"
ARMS = ["c289-1-a", "c289-2-b", "c289-3-b", "c289-4-a"]
COMMIT = "dbb8f9220dde64de546deb3b00732e3089bb7263"
CPP = "e818d71a6f895d8721f1d30c43e40cf113c70884639123ca643867027789346d"
CORE = "5ed0f6531f313205d2d3c74bf4988de004b70571a594d620428972f135399572"
PINS = {
    "raw-manifest.json": "baf4782dbf3b1b909c8b81b1f55e50909e51661ca49bd9ff5a5ae68c1d27eefd",
    "paired-analysis.json": "eff57d29385d0b1c773fa3eba5a2296338680d5b6012b8e918345be01f0b30c2",
    "protocol.json": "b4417a472ccdf57c93a9dc217599293104ad57b185593601df1d4f94f24f4b37",
    "family-receipt.json": "2d35df8fd64769f9460a56eb5fa8b9b759d199f7d41a4cecbcf09c3fcee7aeaa",
}


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def sealed(name, pin, size=None):
    data = (RESULTS / name).read_bytes()
    check(hashlib.sha256(data).hexdigest() == pin and size in (None, len(data)), "input identity")
    return json.loads(data)


def account(report, arm, tier):
    read = report["worker_read_elapsed_s"]
    sets = report["worker_set_elapsed_s"]
    wall = report["service_s"]
    check(len(read) == len(sets) == 4 and report["tier"] == tier, "workers/tier")
    check(
        all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in [*read, *sets, wall]),
        "duration",
    )
    check(
        all(r + s <= wall + 1e-9 for r, s in zip(read, sets, strict=True)), "per-worker occupancy"
    )
    check(
        report["experts_served"] == 256
        and report["destination_verified"] is True
        and report["destination_shape"] == [2880, 2880]
        and report["logical_weight_bytes"] == 256 * 3 * 4406400
        and report["pread_calls"] == (768 if arm == "A" else 256)
        and report["aligned_request_bytes"] >= report["logical_weight_bytes"],
        "work",
    )
    return {
        "wall_s": wall,
        "max_worker_read_s": max(read),
        "sum_worker_read_s": math.fsum(read),
        "sum_worker_set_s": math.fsum(sets),
        "pread_calls": report["pread_calls"],
        "aligned_request_bytes": report["aligned_request_bytes"],
        "bytes_passed_to_three_sets_per_expert": report["logical_weight_bytes"],
    }


def reproduce():
    evidence = {name: sealed(name, sha) for name, sha in PINS.items()}
    protocol = evidence["protocol.json"]
    check(
        evidence["family-receipt.json"]["measurement_commit"] == COMMIT
        and evidence["family-receipt.json"]["returncode"] == 0,
        "original campaign",
    )
    check(
        [r["id"] for r in protocol["runs"]] == ARMS
        and [r["arm"] for r in protocol["runs"]] == list("ABBA"),
        "ABBA",
    )
    check(
        [h for k, h in protocol["file_sha256"].items() if k.endswith("/expert_service_layout.cpp")]
        == [CPP],
        "native source pin",
    )
    cpp = (ROOT / "tools/expert_service_layout.cpp").read_bytes()
    parts = cpp.split(b" // All components revalidated outside timing")
    check(len(parts) == 2 and hashlib.sha256(parts[1]).hexdigest() == CORE, "native timed probe")
    files = evidence["raw-manifest.json"]["files"]
    records = {}
    for name, desc in zip(ARMS, protocol["runs"], strict=True):
        arm = desc["arm"]
        path = str(RESULTS.relative_to(ROOT) / "raw" / f"{name}-service.json")
        check(desc["result_path"].endswith("/" + path), "raw path scope")
        entries = [e for e in files if e["path"] == path]
        check(len(entries) == 1, "raw manifest cardinality")
        entry = entries[0]
        r = sealed(name + "-analysis.json", entry["sha256"], entry["bytes"])
        check(
            r["status"] == "PASS_LOSSLESS_SAMPLE_SERVICE"
            and r["arm"] == arm
            and r["component_checks"] == 384
            and r["source_fd_direct"] is r["pack_fd_direct"] is True
            and len(r["reports"]) == 2,
            "qualified service",
        )
        tiers = {
            tier: account(row, arm, tier)
            for tier, row in zip(("CPU", "GPU"), r["reports"], strict=True)
        }
        records[name] = {"raw": entry, "tiers": tiers}
        if arm == "B":
            cpu, gpu = tiers["CPU"], tiers["GPU"]
            upper = cpu["wall_s"] - cpu["max_worker_read_s"]
            records[name]["conditional_CPU_only"] = {
                "CPU_wall_saving_upper_s": upper,
                "CPU_wall_saving_upper_percent": 100 * upper / cpu["wall_s"],
                "serial_CPU_then_GPU_upper_percent": 100 * upper / (cpu["wall_s"] + gpu["wall_s"]),
                "serial_CPU_then_GPU_floor_s": cpu["max_worker_read_s"] + gpu["wall_s"],
            }
    pairs = {}
    for tier in ("CPU", "GPU"):
        diagnostic = []
        for a, b in ((ARMS[0], ARMS[1]), (ARMS[3], ARMS[2])):
            control = records[a]["tiers"][tier]["wall_s"]
            packed = records[b]["tiers"][tier]["wall_s"]
            gain = 100 * (1 - packed / control)
            diagnostic.append({"arms": [a, b], "packed_vs_original_wall_reduction_percent": gain})
        ref = evidence["paired-analysis.json"]["tiers"][tier]["pairs"]
        check(
            len(ref) == 2
            and all(
                x["arms"] == y["arms"]
                and math.isclose(
                    x["packed_vs_original_wall_reduction_percent"], y["gain_percent"], abs_tol=1e-9
                )
                for x, y in zip(diagnostic, ref, strict=True)
            ),
            "historical paired control",
        )
        pairs[tier] = diagnostic
    return {
        "status": "REPRODUCED_CONDITIONAL_UPPER_BOUND_ACTUAL_GAIN_INCONCLUSIVE",
        "measurement_commit": COMMIT,
        "native_source_sha256": CPP,
        "timed_probe_suffix_sha256": CORE,
        "sealed_sources": PINS,
        "arms": records,
        "historical_control": pairs,
        "wall_saving_scope": "B CPU SET only, fixed reads, assignment and GPU wall",
        "new_forwards": 0,
        "new_expert_reads": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(exist_ok=False)
    try:
        result = reproduce()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(result["status"])
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
