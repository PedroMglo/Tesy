"""Reconstruct the public record for the mixed-CUDA R01 from the original receipts."""

import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(ok, why):
    if not ok:
        raise ValueError(why)


def compact(raw):
    def read(name):
        return json.loads((raw / name).read_bytes())

    family = read("receipt.json")
    require(family["status"] == "FAIL_PRESERVED", "R01 terminal status")
    phases = {}
    for name, expected in (("pre", "PASS_PRE"), ("run", "PASS_RUN"), ("post", "FAIL_PRESERVED")):
        phase = family["phases"][name]
        filename = name + ".json"
        row = read(filename)
        require(phase["receipt_sha256"] == digest(raw / filename), name + " receipt digest")
        require(row["status"] == phase["status"] == expected, name + " status")
        require(row["head"] == family["head"] and row["tree"] == family["tree"], name + " version")
        phases[name] = row

    run, post = phases["run"], phases["post"]
    reference = read_reference()
    require(run["rc"] == 0 and run["clean_compute_pids"] == [], "native exit or cleanup")
    require(digest(raw / "telemetry.jsonl") == run["telemetry_sha256"], "runtime telemetry")
    require(
        digest(raw / ("loads." + str(run["native_pid"]))) == post["loader_log_sha256"], "loader"
    )
    journal = raw / "native/boundary.tsv"
    require(
        digest(journal) == run["journal_sha256"] == reference["boundary_journal_sha256"], "edges"
    )
    sizes = {}
    for n, block in reference["scopes"].items():
        f = raw / "native" / (n + ".f32")
        require(digest(f) == run["outputs_sha256"][n] == block["result_sha256"], "F32")
        sizes[n] = f.stat().st_size
        require(sizes[n] == 8 * block["raw_and_masked_values_each"], "two F32 views")
    required = phases["pre"]["required_sha256"]
    loaded = post["loaded_init_sha256"]
    require(all(loaded.get(name) == sha for name, sha in required.items()), "critical providers")
    auxiliary = post["optional_dl_init_sha256"]
    require(
        "libnvidia-ptxjitcompiler.so.620.73.04" in auxiliary
        and "libnvidia-nvvm70.so.4" in auxiliary,
        "R01 auxiliary pair",
    )
    cg = run["cgroup_final"]
    comparison = post["comparison_with_r0"]
    return dict(
        status=family["status"],
        reason=family["reason"],
        numeric_status="PASS_NUMERIC_MIXED_FIXTURE_ONLY",
        head=family["head"],
        tree=family["tree"],
        receipt_sha256=digest(raw / "receipt.json"),
        protocol_sha256=family["protocol_sha256"],
        supervisor_sha256=family["supervisor_sha256"],
        c55_sha256=family["c55_sha256"],
        c118_duration_s=run["c118"]["duration_s"],
        c118_samples=run["c118"]["sample_count"],
        phases=family["phases"],
        supervised_native_wall_s=run["native_supervised_wall_s"],
        family_wall_s=family["wall_s"],
        executable_sha256=reference["executable_sha256"],
        f32_bytes=sizes,
        outputs_sha256=run["outputs_sha256"],
        boundary_sha256=run["journal_sha256"],
        boundary_witnesses=sum(len(s["cuda_mask_boundary"]) for s in reference["scopes"].values()),
        loader_log_sha256=post["loader_log_sha256"],
        required_sha256=required,
        optional_loads_sha256=auxiliary,
        r0_common_equal=sum(item["equal"] is True for item in comparison.values()),
        r0_differing=[name for name, item in comparison.items() if item["equal"] is False],
        server_objects_absent=[name for name, item in comparison.items() if item["equal"] is None],
        telemetry_sha256=run["telemetry_sha256"],
        peak_bytes=cg["memory_peak"],
        swap_cap_bytes=cg["swap_max"],
        oom=cg["events"]["oom"],
        compute_pids_at_end=run["clean_compute_pids"],
    )


def read_reference():
    path = Path(__file__).resolve().parents[2] / "packed_cpu_mixed/receipts/v3-r02-native.json"
    require(
        digest(path) == "633f12763a9eeeddf13935196efabc6d5c09a5578d7887b0e49874442ec8079d", "V3"
    )
    return json.loads(path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    args = parser.parse_args()
    print(json.dumps(compact(args.raw), sort_keys=True, indent=2, allow_nan=False))
