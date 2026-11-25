"""Execute an admitted, serial C291 CPU layer family from sealed build and input receipts."""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

MIB = 1 << 20
CAP = 4096 * MIB
STOP = 3584 * MIB
FAMILY_S = 720
CHILD_S = 180
ARMS = ("DENSE", "STAGED", "DIRECT")
PASS = "PASS_C291_REAL_CPU_LAYER_FAMILY"
TILE_STATUS = "PASS_C291_CPU0_ROUTED_TILE"
GOLD = "338a790937eb4de5512ea25d55318c4f3971f6f16e9ab89364e93cfe8dd2b428"
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
LIBS = {
    "libggml-cpu.so.0.15.3": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "libggml-base.so.0.15.3": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
}
LIB_CODES = dict(zip(("cpu", "base"), LIBS, strict=True))
CAPTURES = {
    "attn_post_norm",
    "ffn_moe_logits",
    "ffn_moe_logits_biased",
    "ffn_moe_topk",
    "ffn_moe_weights_softmax",
    "ffn_moe_out",
}
FILES = {n + "-0.bin" for n in CAPTURES} | {
    "pack.bin",
    "router.weight",
    "router.bias",
    "gate.bias",
    "down.bias",
    "up.bias",
}
ANCHORS = {
    "packed_cpu_views/receipts/mmid-r01.json": (
        "9ec382f1b92c29fff9ef7ec8bbeabbe99788e0bbfbd6403901b44da41f7e3779"
    ),
    "packed_cpu_views/receipts/mmid-r02.json": (
        "6bb9c4c7cb8c09fb0da05bb74f9454fee7bb68224d8aa874ae25c9f2fd0fcb1c"
    ),
    "packed_cpu_views/receipts/manifest-v2.json": (
        "87126d27fe3e54d8e1a948998c79a6208d1caae64cc20a9e45cb34c6fa5b0ce8"
    ),
    "packed_cpu_views/receipts/dio-v2-verify.json": (
        "65605877aa71e2132fae7bca7723a7da1f7dd2c8e8fa7c9a8d20461609199e2c"
    ),
    "packed_cpu_mixed/receipts/v3-r01-native.json": (
        "26b2136d2bdb023f6126d7c4f8a80ac0e47e2d8a20a05a220615e12aad6f7825"
    ),
    "packed_cpu_mixed/receipts/v3-r02-native.json": (
        "633f12763a9eeeddf13935196efabc6d5c09a5578d7887b0e49874442ec8079d"
    ),
    "packed_worker/receipts/candidate-r01.json": (
        "6823ffc0abbddd8d8653cfee9726358e4670e9543bf327c9a19e22e3b6794875"
    ),
    "packed_worker/receipts/original-r03.json": (
        "6c63aee66a7ebcaa203ee8f7a96376c63a8f97bbf2fd45862988900bf6c3e0af"
    ),
}
REFERENCE = {
    "63bd0fe02a02405da3b23ee799f471f66b78a1864cdad88b354bee6cbc546902",
    "b073d6708e50df31f6f71a4c5dc1b3102222ab23b62215ad0238ffa439ebf4e3",
    "ae0271cda1caca1547d517185a4c74fa16bb10dae393d3032ffb522fd9136dcc",
    "1562f0a38a8cb7663da379f9eb7b016a03f1f2cdc45c766c0c33eead76508e7c",
    "aa71877afd1ce43f1f56988105af75021d649fe842ae47d39402c3a06b0fe5bf",
}
SELF = Path(__file__).resolve()


def need(value, message):
    if not value:
        raise ValueError(message)


def now():
    return dt.datetime.now(dt.UTC).isoformat()


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def sealed_file(path, expected):
    need(
        path.is_file()
        and not path.is_symlink()
        and re.fullmatch("[0-9a-f]{64}", expected)
        and sha(path) == expected,
        "identity:" + path.name,
    )


def sealed_json(path, expected):
    need(path.stat().st_size <= 16 * MIB, "oversize_receipt")
    sealed_file(path, expected)
    return json.loads(path.read_bytes())


def put(path, data):
    tmp = path.with_name(path.name + ".writing")
    with tmp.open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    os.link(tmp, path)
    tmp.unlink()


def command(args, env=None):
    return subprocess.check_output(args, env=env, text=True, timeout=8).strip()


def footprint(root):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def token(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def digests_in(obj):
    if isinstance(obj, str):
        return {obj}
    if isinstance(obj, dict):
        return set().union(*(digests_in(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(digests_in(v) for v in obj))
    return set()


def prepare_gate(a):
    root = a.input_dir
    meta = sealed_json(root / "prepare.json", a.input_sha256)
    need(
        meta["status"] == "PASS_PREPARED_REAL_TILE" and meta["model_sha256"] == MODEL,
        "input_preparation_or_model",
    )
    need(
        meta["gguf_read_bytes"] == meta["gguf_returned_bytes"] == 67743872 <= 80 * MIB
        and meta["gguf_reads"] == 32
        and meta["components_verified"] == 30
        and meta["ordered_experts"] == [45, 49, 57, 60, 98]
        and meta["program_sha256"] == sha(a.checkout / a.study / "prepare.py")
        and REFERENCE <= digests_in(meta["capture_refs"]),
        "weight_reads_or_gold_anchors",
    )
    need(
        meta["model_fd_identity"]
        and meta["pack_identity"]
        and meta["model_mount"]
        and meta["pack_mount"],
        "missing_placement",
    )
    pack = root / "pack.bin"
    pack_stat = token(pack)
    source = meta["pack_identity"]
    need(
        pack_stat == tuple(source[k] for k in ("dev", "ino", "size", "mtime_ns", "ctime_ns"))
        and meta["model_mount"] == meta["pack_mount"]
        and meta["pack_mount"]["filesystem"] == "btrfs"
        and meta["pack_readback_bytes"] == meta["pack_size_bytes"] == pack_stat[2]
        and meta["metadata_sha256"]
        == "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
        and meta["index_sha256"]
        == "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"
        and meta["placement_sha256"]
        == "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7",
        "checked_pack_inode_or_source_identity",
    )
    files = meta["file_sha256"]
    need(
        set(files) == FILES and {p.name for p in root.iterdir()} == FILES | {"prepare.json"},
        "input_manifest_coverage",
    )
    need(
        (root / "pack.bin").stat().st_size == 66293760 <= 80 * MIB
        and footprint(root) - (root / "pack.bin").stat().st_size <= 128 * MIB,
        "input_volumes",
    )
    need(
        meta["prepared_files_bytes"] == sum((root / n).stat().st_size for n in FILES) <= 128 * MIB,
        "input_size",
    )
    for name, digest in files.items():
        sealed_file(root / name, digest)
    gold = root / "ffn_moe_out-0.bin"
    need(files[gold.name] == GOLD and gold.stat().st_size == 153 * 2880 * 4, "canonical_full_FFN")
    with gold.open("rb") as f:
        f.seek(32 * 2880 * 4)
        tile = f.read(32 * 2880 * 4)
    need(all(math.isfinite(v[0]) for v in struct.iter_unpack("<f", tile)), "nonfinite_reference")
    return meta, tile, {p.name: token(p) for p in root.iterdir()}


def child_env(a, arm):
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LD_LIBRARY_PATH": str(a.libs),
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "8",
        "OMP_DYNAMIC": "FALSE",
        "TESY_CPU_WAVE_SKIP_PARKED": "1",
    }
    if arm != "DENSE":
        env["TESY_PACKED_CPU_SLOTS"] = arm.lower()
    return env


def authority(a, r):
    tree = a.checkout
    study = tree / a.study
    git = [
        "git",
        "--no-optional-locks",
        "-c",
        "core.preloadIndex=false",
        "-c",
        "index.threads=1",
        "-C",
        str(tree),
    ]
    need(
        re.fullmatch("[0-9a-f]{40}", a.expect_head)
        and command([*git, "rev-parse", "HEAD"]) == a.expect_head
        and not command([*git, "status", "--porcelain"]),
        "expected_clean_checkout",
    )
    need(
        study.resolve().is_relative_to(tree / "research" / "qualification-retake"),
        "study_outside_checkout",
    )
    names = ["profile.py", "protocol.md", "build.py", "layer.cpp", "slot_witness.h", "prepare.py"]
    sources = {}
    for name in names:
        path = study / name
        git_bytes = subprocess.check_output(
            [*git, "show", a.expect_head + ":" + str(path.relative_to(tree))], timeout=8
        )
        expected = hashlib.sha256(git_bytes).hexdigest()
        sealed_file(path, expected)
        sources[name] = expected
    need(sha(SELF) == sources["profile.py"], "supervisor_not_frozen")
    for path, expected in ANCHORS.items():
        sealed_file(study.parent / path, expected)
    build = sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(re.fullmatch("[0-9a-f]{40}", build["commit"]), "build_commit")
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", build["commit"], a.expect_head], check=True, timeout=8
    )
    for name in ("build.py", "layer.cpp", "slot_witness.h"):
        prior = subprocess.check_output(
            [*git, "show", build["commit"] + ":" + str((study / name).relative_to(tree))], timeout=8
        )
        need(hashlib.sha256(prior).hexdigest() == sources[name], "build_source_different")
    need(
        build["status"] == "PASS_C291_CPU_TILE_BUILD"
        and build["worker_commit"] == "c89c88b342054223e3f27a17fbfd0954803147ac"
        and build["worker_tree"] == "3962daa588dfa89971c60c95ce4c5054bc27fd3f"
        and build["patch_sha256"] == sha(study.parent / "packed_worker/arena.patch")
        and build["helper_source_sha256"] == sha(tree / "tools/block_expert_reuse_operator.cpp")
        and build["libs"] == LIBS
        and set(build["executables"]) == {"arena-layer", "dense-layer"}
        and build["native_sources"]
        == {n: sources[n] for n in ("build.py", "layer.cpp", "slot_witness.h")},
        "native_build_provenance",
    )
    need(len(set(build["executables"].values())) == 2, "independent_dense_missing")
    for name, digest in LIBS.items():
        sealed_file(a.libs / name, digest)
    for name, digest in build["executables"].items():
        binary = a.build_dir / name
        sealed_file(binary, digest)
        linked = command(["/usr/bin/ldd", str(binary)], child_env(a, "DENSE"))
        need(
            "not found" not in linked
            and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", linked),
            "forbidden_ELF",
        )
        mapped = {}
        for line in linked.splitlines():
            parts = line.split()
            if parts[0].startswith("libggml"):
                need(len(parts) >= 3 and parts[1] == "=>", "unknown_ggml_dependency")
                resolved = Path(parts[2]).resolve(strict=True)
                need(
                    resolved.name in LIBS and resolved.samefile(a.libs / resolved.name),
                    "loader_ggml_path",
                )
                mapped[resolved.name] = sha(resolved)
        need(mapped == LIBS, "ggml_loader_incomplete")
    r.update(
        commit=a.expect_head,
        tree=command([*git, "rev-parse", "HEAD^{tree}"]),
        source_sha256=sources,
        build_sha256=a.build_sha256,
        build_commit=build["commit"],
        preparation_sha256=a.input_sha256,
        libraries=LIBS,
        clean_predecessors=ANCHORS,
        executables=build["executables"],
    )
    return study


def verify_arm(a, row, arm, directory, gold):
    expected = dict(
        status=TILE_STATUS,
        arm=arm,
        router_positions=153,
        ffn_positions=32,
        full_ffn_values=92160,
        graph_waves=8,
        active_waves=1,
        mmid_nodes_observed=24,
        compute_backend="CPU",
        weight_sets=0 if arm == "DIRECT" else 15,
        unique_loads=5,
        roles=["gate", "down", "up"],
        logical_weight_bytes=66096000,
        workers_before_destructor=4,
        joined_workers=4,
        manager_destructor_returned=True,
    )
    for k, v in expected.items():
        need(type(row.get(k)) is type(v) and row[k] == v, "native_witness:" + k)
    align = row["dio_offset_alignment"]
    need(type(align) is int and align > 0 and align & (align - 1) == 0, "alignment")
    wanted = ((13219200 + align - 1) // align) * align if arm == "DENSE" else 13221888
    need(row["pread_bytes"] == 5 * wanted, "submitted_read_bytes")
    need(set(row["providers"]) == set(LIB_CODES), "missing_runtime_provider")
    for kind, soname in LIB_CODES.items():
        p = Path(row["providers"][kind])
        need(
            p.is_absolute() and p.samefile(a.libs / soname) and sha(p) == LIBS[soname],
            "runtime_provider:" + kind,
        )
    result = directory / "tile.f32"
    need(
        {p.name for p in directory.iterdir()} == {result.name}
        and not result.is_symlink()
        and result.stat().st_size == len(gold)
        and result.read_bytes() == gold,
        "full_reference_tile",
    )
    return hashlib.sha256(gold).hexdigest()


def scoped(a, out, r, start):
    study = authority(a, r)
    prep, gold, inputs = prepare_gate(a)
    r.update(
        gguf_requested_bytes_in_preparation=prep["gguf_read_bytes"],
        gguf_read_bytes_by_family=0,
        ffntile_gold_sha256=hashlib.sha256(gold).hexdigest(),
        capture_refs=prep["capture_refs"],
        pack_sha256=prep["file_sha256"]["pack.bin"],
        prepared_files_bytes=prep["prepared_files_bytes"],
        c55_receipt_sha256=a.c55_sha256,
        sample_scope="one cgroup for three serial layer subprocesses",
    )
    sys.path.insert(0, str(a.checkout / "tools"))
    import c118_start_inventory as inventory
    import host_resource_policy as policy
    import run_bounded as bounded

    c55 = sealed_json(a.c55_receipt, a.c55_sha256)
    pol = sealed_json(a.c55_receipt.parent / "resource-policy.json", c55["canonical_policy_sha256"])
    sealed_file(a.c55_receipt.parent / "samples.jsonl", c55["window_sha256"])
    for filename, key in (("window.py", "runner_sha256"), ("protocolo.md", "protocol_sha256")):
        sealed_file(study.parent / "nvme_admission" / filename, c55[key])
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and c55["span_s"] >= 60
        and pol == policy.derive_policy(snapshot=pol["snapshot"])
        and min(x["cap_max_bytes"] for x in (c55["canonical_memory"], c55["memory"], pol["memory"]))
        >= CAP,
        "C55",
    )
    resources = policy.freeze_protocol_resource_limits(
        pol, cgroup_memory_max_bytes=CAP, start_mode="CAPACITY_ADMISSION_START"
    )
    need(resources["cgroup"]["memory_stop_bytes"] == STOP, "preventive_margin")
    protocol = {"resources": resources, "limits": {}}
    power = {k: pol["power"][k] for k in ("source", "profile")}
    cg0 = bounded.cgroup_state()
    need(
        cg0
        and cg0["memory_max"] == CAP
        and cg0["swap_max"] == cg0["swap_current"] == 0
        and cg0["path"].endswith("/" + a.unit + ".scope")
        and cg0["memory_peak"] < STOP,
        "cgroup_admission",
    )
    cg = Path("/sys/fs/cgroup") / cg0["path"].lstrip("/")
    monitor = policy.RuntimeGuard(protocol, cg0)
    raw = out / "raw"
    raw.mkdir()
    doc = dict(policy=pol, cap_bytes=CAP, expected_power=power, duration_s=60)
    inv = inventory.collect(out, a.unit, **doc)
    inventory.require_inventory(out, a.unit, inv, max_age_s=3, **doc)
    put(raw / "c118.json", inv)
    r["c118"] = {k: v for k, v in inv.items() if k != "path"}
    obs = inventory.live_sample()
    reasons = policy.validate_start_observation(
        protocol,
        available_bytes=obs["mem_available_bytes"],
        gpu=obs["gpu"],
        thermal=obs["thermal"],
        power=obs["power"],
        psi_full_avg10=policy.host_pressure(),
    )
    need(not reasons, "start_guard:" + str(reasons))
    previous = time.monotonic()

    def sample(telemetry, arm, phase, child=None):
        nonlocal previous
        child_sample = bounded.proc_status(child.pid) if child is not None else {}
        sample_proc = bounded.proc_status(os.getpid())
        cg_state = bounded.cgroup_state()
        need(cg_state, "cgroup_telemetry_missing")
        gpu = bounded.gpu_state(prospective=True)
        thermal = bounded.thermal_state(prospective=True)
        compute = command(
            ["/usr/bin/nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"]
        ).split()
        row = dict(
            arm=arm,
            phase=phase,
            utc=now(),
            cgroup=cg_state,
            gpu=gpu,
            thermal=thermal,
            mem_available_bytes=bounded.mem_available(),
            resource_observation={
                "power": policy.live_power(),
                "host_psi_full_avg10": policy.host_pressure(),
            },
            proc=sample_proc,
            proc_owner="supervisor",
            native_process=child_sample,
            compute_pids=compute,
        )
        stamp = time.monotonic()
        row.update(elapsed_s=stamp - start, gap_s=stamp - previous)
        telemetry.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
        telemetry.flush()
        failed = monitor.check(row)
        need(
            not failed
            and not compute
            and not child_sample.get("VmSwap")
            and row["gap_s"] <= 3
            and row["elapsed_s"] < FAMILY_S,
            str(failed or "compute_swap_cadence_or_wall"),
        )
        # Linux accounts cgroup events between samples, including a short-lived subprocess.
        need(
            int((cg / "memory.swap.peak").read_text()) == 0 and cg_state["memory_peak"] < STOP,
            "memory_peak",
        )
        need(
            footprint(out) + prep["prepared_files_bytes"] - prep["pack_size_bytes"] + 65536
            < 128 * MIB,
            "family_materialized_bytes",
        )
        previous = stamp
        return row

    with (raw / "samples.jsonl").open("x") as telemetry:
        for arm in ARMS:
            need(inputs == {p.name: token(p) for p in a.input_dir.iterdir()}, "inputs_changed")
            executable = a.build_dir / ("dense-layer" if arm == "DENSE" else "arena-layer")
            sealed_file(executable, r["executables"][executable.name])
            sample(telemetry, arm, "before")
            if arm == "DENSE":
                age = (
                    dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(inv["last_utc"])
                ).total_seconds()
                need(0 <= age <= 3, "C118_expired_before_first_spawn")
            slot = out / arm
            slot.mkdir()
            output = slot / "native"
            res = {
                "arm": arm,
                "status": "FAIL_PRESERVED",
                "child_started": False,
                "started_utc": now(),
            }
            r["arms"].append(res)
            tic = time.monotonic()
            child = None
            try:
                with (slot / "stdout").open("xb") as sout, (slot / "stderr").open("xb") as serr:
                    child = subprocess.Popen(
                        [executable, a.input_dir, arm, output],
                        cwd=a.checkout,
                        env=child_env(a, arm),
                        stdout=sout,
                        stderr=serr,
                        start_new_session=True,
                    )
                    res.update(
                        child_started=True,
                        pid=child.pid,
                        executable_sha256=r["executables"][executable.name],
                    )
                    while child.poll() is None:
                        sample(telemetry, arm, "running", child)
                        need(time.monotonic() - tic < CHILD_S, "child_wall_timeout")
                        try:
                            child.wait(timeout=0.20)
                        except subprocess.TimeoutExpired:
                            pass
                    ended = time.monotonic()
                    need(ended - tic <= CHILD_S, "child_wall_timeout")
                    res.update(child_rc=child.returncode, observed_spawn_to_exit_s=ended - tic)
                sample(telemetry, arm, "after")
                need(child.returncode == 0, "native_exit:" + arm)
                row = json.loads((slot / "stdout").read_bytes())
                digest = verify_arm(a, row, arm, output, gold)
                res.update(
                    status=TILE_STATUS,
                    tile_sha256=digest,
                    weight_sets=row["weight_sets"],
                    pread_bytes=row["pread_bytes"],
                    logical_weight_bytes=row["logical_weight_bytes"],
                    joined_workers=row["joined_workers"],
                    provider_sha256=LIBS,
                )
            finally:
                if child is not None:
                    bounded.stop_own_group(child)
                    res["child_rc"] = child.returncode
                res.update(
                    stdout_sha256=sha(slot / "stdout"),
                    stderr_sha256=sha(slot / "stderr"),
                    closed_utc=now(),
                )
                put(slot / "receipt.json", res)
        sample(telemetry, "family", "cleanup")
    need(inputs == {p.name: token(p) for p in a.input_dir.iterdir()}, "inputs_changed_at_cleanup")
    need(
        len({x["tile_sha256"] for x in r["arms"]}) == 1
        and len(r["arms"]) == 3
        and all(x["status"] == TILE_STATUS for x in r["arms"]),
        "family_comparison",
    )
    remaining = sorted(int(p) for p in (cg / "cgroup.procs").read_text().split())
    need(remaining == [os.getpid()], "scope_has_unreaped_processes")
    r.update(
        status=PASS,
        peak_bytes=int((cg / "memory.peak").read_text()),
        swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
        monitor_sha256=sha(raw / "samples.jsonl"),
        cgroup_final=bounded.cgroup_state(),
        cpu_stat=(cg / "cpu.stat").read_text(),
        io_stat=(cg / "io.stat").read_text(),
        child_processes_at_cleanup=0,
    )


def main(a):
    os.umask(0o077)
    need(re.fullmatch(r"tesy-[a-z0-9][a-z0-9-]{1,110}", a.unit), "unit_name")
    out = a.new_output_dir
    start = time.monotonic()
    if not a.in_scope:
        out.mkdir(exist_ok=False)
    r = dict(
        status="FAIL_PRESERVED",
        unit=a.unit,
        arms=[],
        started_utc=now(),
        child_wall_limit_s=CHILD_S,
        family_wall_limit_s=FAMILY_S,
        cgroup_max_bytes=CAP,
        preventive_stop_bytes=STOP,
        swap_max=0,
    )
    try:
        if a.in_scope:
            scoped(a, out, r, start)
        else:
            # systemd owns the family and descendants if the Python monitor itself dies.
            cmd = [
                "/usr/bin/systemd-run",
                "--user",
                "--scope",
                "--quiet",
                "--collect",
                "--unit=" + a.unit,
                "-p",
                f"MemoryMax={CAP}",
                "-p",
                "MemorySwapMax=0",
                "-p",
                f"RuntimeMaxSec={FAMILY_S}s",
                "-p",
                "CPUAccounting=yes",
                "-p",
                "IOAccounting=yes",
                sys.executable,
                "-I",
                "-B",
                str(SELF),
                *sys.argv[1:],
                "--in-scope",
            ]
            with (out / "scope.stdout").open("xb") as so, (out / "scope.stderr").open("xb") as se:
                completed = subprocess.run(cmd, stdout=so, stderr=se, timeout=FAMILY_S + 8)
            r["scope_exit"] = completed.returncode
            detail = out / "detail.json"
            if detail.is_file():
                r["detail_sha256"] = sha(detail)
                r["detail"] = json.loads(detail.read_bytes())
                r["arms"] = r["detail"]["arms"]
            need(
                completed.returncode == 0 and r.get("detail", {}).get("status") == PASS,
                "scope_or_family_failed",
            )
            r["status"] = PASS
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        r.update(supervisor_sha256=sha(SELF), closed_utc=now(), elapsed_s=time.monotonic() - start)
        put(out / ("detail.json" if a.in_scope else "receipt.json"), r)
    print(r["status"], flush=True)
    return int(r["status"] != PASS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("checkout", "build-dir", "input-dir", "libs", "c55-receipt", "new-output-dir"):
        parser.add_argument("--" + key, type=lambda x: Path(x).absolute(), required=True)
    parser.add_argument("--study", default="research/qualification-retake/packed_real_layer")
    for key in ("expect-head", "build-sha256", "input-sha256", "c55-sha256", "unit"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--in-scope", action="store_true", help=argparse.SUPPRESS)
    sys.exit(main(parser.parse_args()))
