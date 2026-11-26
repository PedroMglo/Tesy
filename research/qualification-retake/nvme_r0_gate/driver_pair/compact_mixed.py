"""Reconstruct the public record for either frozen mixed-CUDA campaign."""

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path, PurePosixPath


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(ok, why):
    if not ok:
        raise ValueError(why)


ORIGINAL = "3220c1d499871199861f239a71e956f2b405e15b95d4736dc898f6388c7c746d"
HOMOGENEOUS = "2ff36fbffe14835e7a5db93195ea4a515a2af92e68215528d167da94aa97b147"
PASS = "PASS_C269_MIXED_KERNEL_SINGLE_DRIVER_DEPLOYMENT_ONLY"


def module(path, name, fingerprint):
    require(digest(path) == fingerprint, "verification code identity")
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def archived_initializers(log, pid, links, signed, files, post_digests):
    """Look up exact loader strings in the sealed pre/post maps, without accessing their paths."""
    literals = {}

    def bind(literal, target):
        p = PurePosixPath(literal)
        require(
            p.is_absolute() and str(p) == literal and ".." not in p.parts,
            "invalid absolute literal",
        )
        require(
            target in files and (literal not in literals or literals[literal] == target),
            "unknown or conflicting alias",
        )
        literals[literal] = target

    for soname, (literal, target) in links.items():
        require(PurePosixPath(literal).name == soname, "changed literal SONAME")
        bind(literal, target)
    original, driver = links["libcuda.so.1"]
    parent = PurePosixPath(original).parent
    require(
        parent.name == "driver" and driver == str(signed["libcuda.so.1"]),
        "original private driver directory",
    )
    for name, target in signed.items():
        require(PurePosixPath(name).name == name, "invalid frozen driver SONAME")
        bind(str(parent / name), str(target))

    loaded = set()
    for line in log.splitlines():
        if "calling init:" not in line:
            continue
        m = re.fullmatch(r"\s*(\d+):\s+calling init:\s*(/.+?)\s*", line)
        require(
            m is not None and int(m[1]) == pid and m[2] in literals, "unbound loader init or PID"
        )
        loaded.add(literals[m[2]])
    hashes = {PurePosixPath(path).name: files[path]["sha256"] for path in loaded}
    require(
        loaded and len(hashes) == len(loaded) and hashes == post_digests,
        "resolved initializers disagree with sealed postflight",
    )
    return loaded


def homogeneous(raw, study, phases, reference):
    pre, run, post = (phases[n] for n in ("pre", "run", "post"))
    authority = study / "driver_origin.json"
    pin = "0d2b2ad1503c15bb5829ec96d5e6c55b307d5545fd4fe39537607b8e8f5bae44"
    require(
        digest(authority) == pre["driver_audit_sha256"] == post["driver_audit_sha256"] == pin,
        "origin proof",
    )
    audit = json.loads(authority.read_bytes())
    core = module(study / "profile.py", "sealed_mixed_controller", run["supervisor_sha256"])
    origin = module(
        study / "driver_origin.py",
        "sealed_driver_origin",
        core.HOMOGENEOUS_PINS["driver_origin.py"],
    )
    meta = audit["providers"]
    require(
        pre["signed_deployment"] == audit["deployment"]["commit"] == origin.COMMIT
        and run["monitor_provider"]["actual_nvml_sha256"] == meta[origin.MON]["sha256"]
        and run["monitor_provider"]["kernel_driver"] == audit["kernel"]["release"],
        "driver deployment/monitor",
    )
    pid = run["native_pid"]
    trace = (raw / f"loads.{pid}").read_text()
    searched = origin.all_requests(trace, pid)
    require(
        sorted(searched) == post["all_search_names"]
        and searched <= set(audit["r01_all_search_names"]),
        "search evidence",
    )
    signed = {n: origin.LIB / meta[n]["file"] for n in origin.ORDER}
    require(digest(raw / "static-map.json") == pre["static_sha256"], "original static map")
    static = json.loads((raw / "static-map.json").read_bytes())
    loaded = archived_initializers(
        trace, pid, static["links"], signed, static["files"], post["loaded_init_sha256"]
    )
    observed = origin.validate_driver_log(origin.requests(trace, pid), loaded, signed)
    require(
        observed == post["runtime_driver"] and not observed[origin.ABSENT]["initialized"],
        "runtime proof",
    )
    require(
        len(static["links"]) == pre["linked_r01_sha256_verified"] == len(audit["r01_startup"]),
        "startup identity count",
    )
    for n, row in audit["r01_startup"].items():
        _, real = static["links"][n]
        require(
            Path(real).name == row["filename"] and static["files"][real]["sha256"] == row["sha256"],
            "startup authority",
        )
    for n, path in signed.items():
        h = meta[n]["sha256"]
        require(
            static["files"][str(path)]["sha256"] == h == pre["candidate_driver_sha256"][n],
            "file origin",
        )
        if observed[n]["initialized"]:
            require(post["loaded_init_sha256"].get(path.name) == h, "activated candidate")
    mixed = module(
        study.parents[1] / "packed_cpu_mixed/run.py", "v3_native_gold", reference["runner_sha256"]
    )
    libs = Path((raw / "native/providers.txt").read_text().splitlines()[0]).parent
    scope = {str(k): v for k, v in mixed.verify_native(raw, libs).items()}
    require(
        scope == reference["scopes"]
        and sum(len(v["cuda_mask_boundary"]) for v in scope.values()) == 18,
        "V3 observations",
    )
    cg = run["cgroup_final"]
    require(
        cg["memory_max"] == 1 << 30
        and cg["memory_peak"] < 512 << 20
        and cg["swap_max"]
        == cg["swap_current"]
        == cg["events"]["oom"]
        == cg["events"]["oom_kill"]
        == 0,
        "resources",
    )
    return dict(
        driver_origin_sha256=pin,
        ostree_commit=origin.COMMIT,
        kernel=audit["kernel"],
        driver_objects={
            n: observed[n]
            | dict(
                sha256=meta[n]["sha256"],
                build_id=meta[n]["build_id"],
                ostree_file_object=meta[n]["ostree_file_object"],
            )
            for n in origin.ORDER
        },
        absent_lookup=observed[origin.ABSENT] | {"soname": origin.ABSENT},
        startup_dependencies_verified=pre["linked_r01_sha256_verified"],
        native_search_count=len(searched),
        native_init_count=len(loaded),
        static_unique_elf_bytes=post["static_unique_elf_bytes"],
        nvml_monitor_sha256=run["monitor_provider"]["actual_nvml_sha256"],
        stdout_sha256=digest(raw / "stdout.txt"),
        stderr_sha256=digest(raw / "stderr.txt"),
        all_v3_numeric_scopes_verified=True,
    )


def compact(raw, study=None):
    study = study or Path(__file__).resolve().parent

    def read(name):
        return json.loads((raw / name).read_bytes())

    family = read("receipt.json")
    run_digest = digest(raw / "receipt.json")
    require(run_digest in (ORIGINAL, HOMOGENEOUS), "unknown campaign receipt")
    is_r02 = run_digest == HOMOGENEOUS
    require(family["status"] == (PASS if is_r02 else "FAIL_PRESERVED"), "frozen terminal status")
    phases = {}
    for name, expected in (
        ("pre", "PASS_PRE"),
        ("run", "PASS_RUN"),
        ("post", "PASS_POST" if is_r02 else "FAIL_PRESERVED"),
    ):
        phase = family["phases"][name]
        filename = name + ".json"
        row = read(filename)
        require(phase["receipt_sha256"] == digest(raw / filename), name + " receipt digest")
        require(row["status"] == phase["status"] == expected, name + " status")
        require(row["head"] == family["head"] and row["tree"] == family["tree"], name + " version")
        phases[name] = row

    run, post = phases["run"], phases["post"]
    reference = read_reference(study)
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
    if not is_r02:
        require(
            "libnvidia-ptxjitcompiler.so.620.73.04" in auxiliary
            and "libnvidia-nvvm70.so.4" in auxiliary,
            "R01 auxiliary pair",
        )
    cg = run["cgroup_final"]
    comparison = post["comparison_with_r0"]
    record = dict(
        status=family["status"],
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

    if is_r02:
        record.update(homogeneous(raw, study, phases, reference))
    else:
        record["reason"] = family["reason"]
    return record


def read_reference(study):
    path = study.parents[1] / "packed_cpu_mixed/receipts/v3-r02-native.json"
    require(
        digest(path) == "633f12763a9eeeddf13935196efabc6d5c09a5578d7887b0e49874442ec8079d", "V3"
    )
    return json.loads(path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--study", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(compact(args.raw, args.study), sort_keys=True, indent=2, allow_nan=False))
