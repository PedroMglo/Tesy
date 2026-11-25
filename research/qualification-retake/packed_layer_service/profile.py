"""Physical controller of 36 fresh CPU-only C291 service managers in one cgroup."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

SELF = Path(__file__).resolve()
MIB = 1 << 20
CAP = 4096 * MIB
STOP = 3584 * MIB
MAX_OUT = 32 * MIB
WALL = 720
CHILD_WALL = 180
PRIOR = Path("research/qualification-retake/packed_real_layer")
PRIOR_PROFILE = "3dfc12a50909fddd285143023a2edff5cd6e25b087453f21d4950649618db7cb"
PRIOR_RESULT = "8c328725c320e59cadddb63cb1c522a36f3959e6dad7029c9ff9e1c833e3e220"
PASS = "PASS_C291_MEASURED_FIVE_MISS_FAMILY"


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def clock():
    return dt.datetime.now(dt.UTC).isoformat()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(path, value):
    tmp = path.with_suffix(path.suffix + ".pending")
    with tmp.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    os.link(tmp, path)
    tmp.unlink()


def frozen(project, path, head):
    blob = subprocess.check_output(
        [
            "git",
            "--no-optional-locks",
            "-C",
            project,
            "show",
            head + ":" + str(path.relative_to(project)),
        ],
        timeout=8,
    )
    digest = hashlib.sha256(blob).hexdigest()
    need(not path.is_symlink() and sha(path) == digest, "frozen_source:" + path.name)
    return digest


def validate_build(a, prior, study, r):
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C291_FIVE_MISS_SERVICE_BUILD"
        and build["libs"] == prior.LIBS
        and build["worker_commit"] == "c89c88b342054223e3f27a17fbfd0954803147ac"
        and build["worker_tree"] == "3962daa588dfa89971c60c95ce4c5054bc27fd3f"
        and build["patch_sha256"] == sha(study.parent / "packed_worker/arena.patch")
        and set(build["executables"]) == {"dense-service", "arena-service"}
        and len(set(build["executables"].values())) == 2,
        "service_build_or_original",
    )
    need(re.fullmatch("[0-9a-f]{40}", build["commit"]) and build["native_sources"], "build_sources")
    subprocess.run(
        [
            "git",
            "--no-optional-locks",
            "-C",
            a.checkout,
            "merge-base",
            "--is-ancestor",
            build["commit"],
            a.expect_head,
        ],
        check=True,
        timeout=8,
    )
    for name, digest in build["native_sources"].items():
        need(
            Path(name).name == name
            and frozen(a.checkout, study / name, build["commit"]) == digest
            and frozen(a.checkout, study / name, a.expect_head) == digest,
            "compiled_source_changed",
        )
    for name, digest in prior.LIBS.items():
        prior.sealed_file(a.libs / name, digest)
    library_maps = {}
    for n, h in build["executables"].items():
        exe = a.build_dir / n
        prior.sealed_file(exe, h)
        linked = prior.command(["/usr/bin/ldd", str(exe)], prior.child_env(a, "DENSE"))
        need(
            "not found" not in linked
            and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", linked),
            "forbidden_dependency",
        )
        mapped = {}
        for line in linked.splitlines():
            fields = line.split()
            if fields[0].startswith(("libggml", "libcrypto")):
                need(len(fields) > 2 and fields[1] == "=>", "loader_line")
                path = Path(fields[2]).resolve(strict=True)
                digest = sha(path)
                if fields[0].startswith("libggml"):
                    need(
                        path.name in prior.LIBS
                        and path.samefile(a.libs / path.name)
                        and digest == prior.LIBS[path.name],
                        "loader_GGML",
                    )
                    mapped[path.name] = digest
                else:
                    need(digest == build["crypto_sha256"], "loader_crypto")
                    mapped["libcrypto"] = digest
        need(set(mapped) == set(prior.LIBS) | {"libcrypto"}, "incomplete_loader")
        library_maps[n] = mapped
    r.update(
        build_sha256=a.build_sha256,
        build_commit=build["commit"],
        executable_sha256=build["executables"],
        libraries=library_maps,
    )
    return build


def inputs(a, prior, r):
    authority = prior.sealed_json(a.checkout / PRIOR / "physical-r01/receipt.json", PRIOR_RESULT)
    need(
        authority["status"] == "PASS_C291_REAL_CPU_LAYER_FAMILY"
        and [arm["arm"] for arm in authority["arms"]] == ["DENSE", "STAGED", "DIRECT"]
        and {arm["tile_sha256"] for arm in authority["arms"]}
        == {"bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24"}
        and a.input_sha256 == authority["preparation_sha256"],
        "antecedent_or_new_input",
    )
    # The prior verifier authenticates all prepared bytes; it does not open a GGUF.
    clone = argparse.Namespace(**(vars(a) | {"study": str(PRIOR)}))
    prep, _, files = prior.prepare_gate(clone)
    need(prep["file_sha256"]["pack.bin"] == authority["pack_sha256"], "new_pack")
    r.update(
        input_sha256=a.input_sha256,
        pack_sha256=authority["pack_sha256"],
        numerical_gate_sha256=PRIOR_RESULT,
        gguf_opened_by_family=False,
    )
    return prep, files


def admit(a, prior, study, r, root):
    sys.path.insert(0, str(a.checkout / "tools"))
    import c118_start_inventory as inv
    import host_resource_policy as policy
    import run_bounded as bounded

    c55 = prior.sealed_json(a.c55_receipt, a.c55_sha256)
    pol = prior.sealed_json(
        a.c55_receipt.parent / "resource-policy.json", c55["canonical_policy_sha256"]
    )
    prior.sealed_file(a.c55_receipt.parent / "samples.jsonl", c55["window_sha256"])
    for n, k in [("window.py", "runner_sha256"), ("protocolo.md", "protocol_sha256")]:
        prior.sealed_file(study.parent / "nvme_admission" / n, c55[k])
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and c55["span_s"] >= 60
        and pol == policy.derive_policy(snapshot=pol["snapshot"])
        and min(r["cap_max_bytes"] for r in (c55["canonical_memory"], c55["memory"], pol["memory"]))
        >= CAP,
        "C55",
    )
    resource = policy.freeze_protocol_resource_limits(
        pol, cgroup_memory_max_bytes=CAP, start_mode="CAPACITY_ADMISSION_START"
    )
    protocol = {"resources": resource, "limits": {}}
    baseline = bounded.cgroup_state()
    need(
        resource["cgroup"]["memory_stop_bytes"] == STOP
        and baseline
        and baseline["memory_peak"] < STOP
        and baseline["memory_max"] == CAP
        and baseline["swap_max"] == baseline["swap_current"] == 0
        and baseline["path"].endswith("/" + a.unit + ".scope"),
        "scope_before_C118",
    )
    guard = policy.RuntimeGuard(protocol, baseline)
    power = {k: pol["power"][k] for k in ("source", "profile")}
    kwargs = dict(policy=pol, cap_bytes=CAP, expected_power=power, duration_s=60)
    c118 = inv.collect(root, a.unit, **kwargs)
    inv.require_inventory(root, a.unit, c118, max_age_s=3, **kwargs)
    r["c118"] = {k: v for k, v in c118.items() if k != "path"}
    r["c55_sha256"] = a.c55_sha256
    obs = inv.live_sample()
    reasons = policy.validate_start_observation(
        protocol,
        available_bytes=obs["mem_available_bytes"],
        gpu=obs["gpu"],
        thermal=obs["thermal"],
        power=obs["power"],
        psi_full_avg10=policy.host_pressure(),
    )
    need(not reasons, "start_guard:" + str(reasons))
    return guard, policy, bounded, Path("/sys/fs/cgroup") / baseline["path"].lstrip("/")


class Monitor:
    def __init__(self, guard, policy, bounded, cg, raw, start, elapsed_limit=WALL):
        self.guard, self.policy, self.bounded, self.cg = guard, policy, bounded, cg
        self.raw, self.start, self.elapsed_limit = raw, start, elapsed_limit
        self.error = None
        self.end = threading.Event()
        self.last = time.monotonic()
        self.count = 0

    def observe(self, stream):
        b, p = self.bounded, self.policy
        gpu = b.gpu_state(prospective=True)
        thermal = b.thermal_state(prospective=True)
        compute = subprocess.check_output(
            ["/usr/bin/nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            text=True,
            timeout=3,
        ).split()
        row = dict(
            utc=clock(),
            gpu=gpu,
            thermal=thermal,
            compute_pids=compute,
            cgroup=b.cgroup_state(),
            proc=b.proc_status(os.getpid()),
            proc_owner="supervisor",
            mem_available_bytes=b.mem_available(),
            resource_observation={
                "power": p.live_power(),
                "host_psi_full_avg10": p.host_pressure(),
            },
        )
        stamp = time.monotonic()
        row.update(elapsed_s=stamp - self.start, gap_s=stamp - self.last)
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        self.count += 1
        need(
            row["cgroup"]
            and not compute
            and row["gap_s"] <= 3
            and row["elapsed_s"] < self.elapsed_limit,
            "compute_cadence_or_time",
        )
        reason = self.guard.check(row)
        need(not reason, str(reason))
        self.last = stamp

    def run(self):
        try:
            with self.raw.open("x") as f:
                while True:
                    self.observe(f)
                    if self.end.wait(0.55):
                        self.observe(f)
                        break
        except Exception as error:
            self.error = error
            self.end.set()

    def check(self):
        if self.error is not None:
            raise self.error
        need(time.monotonic() - self.start < WALL, "family_timeout")
        need(time.monotonic() - self.last <= 3, "telemetry_not_live")
        need(
            int((self.cg / "memory.peak").read_text()) < STOP
            and int((self.cg / "memory.swap.peak").read_text()) == 0,
            "cgroup_memory_peak_or_swap",
        )


def monitor_provider(prior):
    need(
        not os.environ.get("LD_PRELOAD") and not os.environ.get("LD_AUDIT"),
        "unexpected_global_interposer",
    )
    override = os.environ.get("LD_LIBRARY_PATH")
    cli = Path("/usr/bin/nvidia-smi")
    kpath = Path("/sys/module/nvidia/version")
    kernel = kpath.read_text().strip()
    src = None
    if override:
        base = Path(override)
        need(
            ":" not in override
            and base.is_absolute()
            and base.resolve(strict=True) == base
            and {q.name for q in base.iterdir()} == {"libnvidia-ml.so.1"},
            "monitor_only_library_path",
        )
        alias = base / "libnvidia-ml.so.1"
        meta = json.loads((base.parent / "receipt.json").read_bytes())
        need(
            alias.is_symlink()
            and meta["status"] == "PASS_CPU_CAMPAIGN_MONITOR"
            and meta["loader_verified"] is True
            and meta["reported_driver"] == meta["kernel_driver"] == kernel == "620.70.06"
            and meta["nvml_sha256"]
            == "1b310cec5baddefef24c0d4b6cec982f1a58e2cc77454de7f7da9809bd9e9ad3"
            and meta["nvidia_smi_sha256"]
            == "616dd34c46398fdd01b73eea69bef30d1388698d494a6e2bc187857f38a938ea"
            and sha(cli) == meta["nvidia_smi_sha256"],
            "monitor_compatibility_receipt",
        )
        src = alias.resolve(strict=True)
        need(sha(src) == meta["nvml_sha256"], "monitor_active_elf")
    probe = subprocess.run(
        [cli, "--query-gpu=driver_version", "--format=csv,noheader,nounits"],
        env=os.environ | {"LD_DEBUG": "libs"},
        capture_output=True,
        text=True,
        timeout=8,
        check=True,
    )
    rows = {
        Path(line.split("calling init:")[-1].strip()).resolve(strict=True)
        for line in probe.stderr.splitlines()
        if "calling init:" in line and "libnvidia-ml.so" in line.split("calling init:")[-1]
    }
    need(len(rows) == 1 and probe.stdout.strip() == kernel, "monitor_active_driver")
    observed = rows.pop()
    need(src is None or observed.samefile(src), "monitor_active_library")
    cli_token, lib_token = prior.token(cli), prior.token(observed)

    def unchanged():
        need(
            kernel == kpath.read_text().strip()
            and cli_token == prior.token(cli)
            and lib_token == prior.token(observed),
            "monitor_provider_changed",
        )
        if override:
            need(
                {q.name for q in base.iterdir()} == {"libnvidia-ml.so.1"}
                and alias.samefile(observed),
                "monitor_override_changed",
            )

    receipt = dict(
        kernel_driver=kernel,
        actual_nvml_sha256=sha(observed),
        nvidia_smi_sha256=sha(cli),
        mode="PRIVATE_MATCHED_NVML" if override else "SYSTEM_NVML",
    )
    if override:
        receipt["monitor_receipt_sha256"] = sha(base.parent / "receipt.json")
    return receipt, unchanged


def prefault_telemetry(native):
    fields = native.get("prefault_faults")
    need(
        isinstance(fields, dict) and fields.get("scope") == "RUSAGE_SELF",
        "missing_or_wrong_prefault_faults_scope",
    )
    required = {"scope"} | {
        kind + "_" + key for kind in ("minflt", "majflt") for key in ("before", "after", "delta")
    }
    need(
        set(fields) == required
        and all(type(fields[k]) is int and fields[k] >= 0 for k in required - {"scope"}),
        "prefault_faults_schema",
    )
    for kind in ("minflt", "majflt"):
        need(
            fields[kind + "_after"] - fields[kind + "_before"] == fields[kind + "_delta"],
            "prefault_faults_conservation",
        )
    return dict(fields)


def verify(a, prior, native, layout, mode):
    expected = {
        "status": "PASS_C291_FIVE_MISS_SERVICE",
        "schema": "tesy-c291-five-misses-v1",
        "layout": layout,
        "observer": mode,
        "clock": "MONOTONIC_RAW_NS",
        "ready_workers": 4,
        "workers_before_destructor": 4,
        "joined_workers": 4,
        "load_count": 5,
        "requested_bytes": 66109440,
        "logical_bytes": 66096000,
        "set_count": 0 if layout == "DIRECT" else 15,
        "queue_empty": True,
        "verified_payload": True,
        "prefault_bytes": 40 * (13219200 if layout == "DENSE" else 13221888),
    }
    for k, v in expected.items():
        need(type(native.get(k)) is type(v) and native[k] == v, "native_witness:" + k)
    ts = [native[k] for k in ("outer_start", "t0", "last_publication", "resume", "outer_end")]
    need(
        all(type(x) is int and x > 0 for x in ts) and ts[0] <= ts[1] < ts[2] <= ts[3] <= ts[4],
        "native_clock_order",
    )
    need(native["prefault_ns"] > 0, "prefault_duration")
    slots = native["confirmed_slots"]
    need(
        [s[0] for s in slots] == [45, 60, 98, 57, 49]
        and len({s[1] for s in slots}) == 5
        and all(
            len(s) == 3 and all(type(v) is int for v in s) and 0 <= s[1] < 40 and s[2] == 1
            for s in slots
        ),
        "FIFO_work_or_generations",
    )
    for kind, name in prior.LIB_CODES.items():
        provider = Path(native["providers"][kind])
        need(
            provider.is_absolute()
            and provider.samefile(a.libs / name)
            and sha(provider) == prior.LIBS[name],
            "native_provider:" + kind,
        )
    need((mode == "MIN") == (native["events"] == []), "observer_mode")
    return dict(
        prefault_faults=prefault_telemetry(native),
        publish_ns=ts[2] - ts[1],
        resume_ns=ts[3] - ts[1],
        post_publish_to_resume_ns=ts[3] - ts[2],
        outer_ns=ts[4] - ts[0],
        prefault_ns=native["prefault_ns"],
        prefault_bytes=native["prefault_bytes"],
        requested_bytes=native["requested_bytes"],
        set_count=native["set_count"],
        slots=slots,
    )


def child(a, r, prior, review, monitor, plan, seq):
    block, layout, mode = plan
    directory = a.new_output_dir / f"{seq:02d}-{layout}-{mode}"
    directory.mkdir()
    original = layout == "DENSE"
    name = "dense-service" if original else "arena-service"
    binary = a.build_dir / name
    prior.sealed_file(binary, r["executable_sha256"][name])
    env = prior.child_env(a, layout)
    need(env["LD_LIBRARY_PATH"] == str(a.libs) and "LD_PRELOAD" not in env, "native_env")
    rec = dict(
        block=block,
        layout=layout,
        observer=mode,
        started_utc=clock(),
        status="FAIL_PRESERVED",
        executable_sha256=r["executable_sha256"][name],
        child_started=False,
    )
    r["arms"].append(rec)
    proc = None
    start = time.monotonic()
    try:
        monitor.check()
        if seq == 1:
            age = (
                dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(r["c118"]["last_utc"])
            ).total_seconds()
            need(0 <= age <= 3, "stale_C118_before_first_spawn")
        with (
            (directory / "stdout").open("xb") as stdout,
            (directory / "stderr").open("xb") as stderr,
        ):
            proc = subprocess.Popen(
                [binary, a.input_dir, layout, mode, directory / "native"],
                env=env,
                cwd=a.checkout,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            rec.update(pid=proc.pid, child_started=True)
            while proc.poll() is None:
                monitor.check()
                need(
                    time.monotonic() - start < CHILD_WALL
                    and prior.footprint(a.new_output_dir) + 65536 < MAX_OUT,
                    "child_wall_or_output_limit",
                )
                try:
                    proc.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    pass
            rec.update(child_rc=proc.returncode, spawn_to_observed_exit_s=time.monotonic() - start)
            need(
                proc.returncode == 0 and rec["spawn_to_observed_exit_s"] <= CHILD_WALL,
                "child_failed",
            )
        need(
            (directory / "stdout").read_text().strip() == "PASS_C291_FIVE_MISS_SERVICE",
            "stdout_terminal",
        )
        out = directory / "native"
        need({f.name for f in out.iterdir()} == {"service.json"}, "native_outputs")
        receipt = out / "service.json"
        need(not receipt.is_symlink() and receipt.stat().st_size < 2 * MIB, "native_size_or_type")
        doc = json.loads(receipt.read_bytes())
        info = verify(a, prior, doc, layout, mode)
        detail = review.review_arm(doc)
        need(
            isinstance(detail, dict)
            and detail["publication_ns"] == info["publish_ns"]
            and detail["resume_ns"] == info["resume_ns"]
            and detail["outer_ns"] == info["outer_ns"],
            "independent_review_of_endpoints",
        )
        rec.update(**info, review=detail, native_receipt_sha256=sha(receipt), status=doc["status"])
        monitor.check()
    finally:
        if proc is not None:
            monitor.bounded.stop_own_group(proc)
            rec["child_rc"] = proc.returncode
        for name in ("stdout", "stderr"):
            if (directory / name).is_file():
                rec[name + "_sha256"] = sha(directory / name)
        rec["closed_utc"] = clock()
        save(directory / "receipt.json", rec)


def scoped(a, r, start):
    root = a.new_output_dir
    here = a.checkout / a.study
    need(
        a.checkout.is_absolute()
        and here.resolve().is_relative_to(a.checkout / "research/qualification-retake"),
        "measurement_checkout",
    )
    git = [
        "git",
        "--no-optional-locks",
        "-c",
        "core.preloadIndex=false",
        "-c",
        "index.threads=1",
        "-C",
        a.checkout,
    ]
    need(
        re.fullmatch("[0-9a-f]{40}", a.expect_head)
        and subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip() == a.expect_head
        and not subprocess.check_output([*git, "status", "--porcelain"]),
        "expected_clean_checkout",
    )
    source = {
        n: frozen(a.checkout, here / n, a.expect_head)
        for n in (
            "protocol.md",
            "r02.md",
            "profile.py",
            "decision.py",
            "review.py",
            "service.cpp",
            "build.py",
            "monitor_library.py",
        )
    }
    need(source["profile.py"] == sha(SELF), "supervisor_identity")
    previous = a.checkout / PRIOR / "profile.py"
    need(
        frozen(a.checkout, previous, a.expect_head) == PRIOR_PROFILE,
        "anchored_resources_or_input_code",
    )
    prior = load(previous, "c291_prior")
    decide = load(here / "decision.py", "c291_service_decision")
    review = load(here / "review.py", "c291_service_review")
    r.update(
        commit=a.expect_head,
        tree=prior.command([*git, "rev-parse", "HEAD^{tree}"]),
        source_sha256=source,
    )
    validate_build(a, prior, here, r)
    prep, files = inputs(a, prior, r)
    r["monitor_provider"], unchanged = monitor_provider(prior)
    (root / "raw").mkdir()
    guard, policy, bounded, cg = admit(a, prior, here, r, root)
    monitor = Monitor(guard, policy, bounded, cg, root / "raw/samples.jsonl", start)
    thread = threading.Thread(target=monitor.run, daemon=True)
    thread.start()
    try:
        for seq, plan in enumerate(decide.schedule(), 1):
            unchanged()
            need(
                files == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
                "inputs_changed_between_arms",
            )
            child(a, r, prior, review, monitor, plan, seq)
            need(r["arms"][-1]["slots"] == r["arms"][0]["slots"], "different_physical_assignment")
        need(
            sha(a.input_dir / "pack.bin") == r["pack_sha256"]
            and files == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
            "pack_final_hash",
        )
        unchanged()
    finally:
        monitor.end.set()
        thread.join(timeout=6)
        r["monitor_samples"] = monitor.count
        need(not thread.is_alive(), "monitor_cleanup")
        monitor.check()
    remaining = (cg / "cgroup.procs").read_text().split()
    need(remaining == [str(os.getpid())], "unfinished_process")
    need(
        sum(a["requested_bytes"] for a in r["arms"]) == 2379939840 and monitor.count >= 2,
        "service_bytes_or_monitor",
    )
    r.update(
        assessment=decide.screen(r["arms"]),
        closure="all_36_processes_joined",
        prepared_pack_bytes=prep["pack_size_bytes"],
        requested_service_bytes=2379939840,
        peak_bytes=int((cg / "memory.peak").read_text()),
        swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
        io_stat=(cg / "io.stat").read_text(),
        cpu_stat=(cg / "cpu.stat").read_text(),
        monitor_sha256=sha(monitor.raw),
        cgroup_end=bounded.cgroup_state(),
    )
    compact_estimate = len(json.dumps(r).encode()) * 4
    need(prior.footprint(root) + compact_estimate + 65536 < MAX_OUT, "family_output_closure")
    r["status"] = PASS


def main(a):
    os.umask(0o077)
    need(re.fullmatch(r"tesy-[a-z0-9][a-z0-9-]{1,110}", a.unit), "unit")
    root = a.new_output_dir
    if not a.in_scope:
        root.mkdir(exist_ok=False)
    tic = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        unit=a.unit,
        arms=[],
        started_utc=clock(),
        cgroup_cap_bytes=CAP,
        cgroup_stop_bytes=STOP,
        swap_max=0,
        wall_limit_s=WALL,
        child_wall_limit_s=CHILD_WALL,
    )
    try:
        if a.in_scope:
            scoped(a, r, tic)
        else:
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
                f"RuntimeMaxSec={WALL}s",
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
            with (root / "scope.stdout").open("xb") as so, (root / "scope.stderr").open("xb") as se:
                rc = subprocess.run(
                    cmd, env=os.environ.copy(), stdout=so, stderr=se, timeout=WALL + 8
                ).returncode
            r["scope_rc"] = rc
            if (root / "detail.json").is_file():
                detail = json.loads((root / "detail.json").read_bytes())
                r.update(
                    detail_sha256=sha(root / "detail.json"),
                    arms_started=sum(x["child_started"] for x in detail["arms"]),
                    group_status=detail["status"],
                    group_reason=detail.get("reason"),
                )
                r["assessment"] = detail.get("assessment")
            need(rc == 0 and r.get("group_status") == PASS, "scope_or_family_failed")
            r["status"] = PASS
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        r.update(supervisor_sha256=sha(SELF), elapsed_s=time.monotonic() - tic, closed_utc=clock())
        save(root / ("detail.json" if a.in_scope else "receipt.json"), r)
    print(r["status"], flush=True)
    return int(r["status"] != PASS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("checkout", "build-dir", "input-dir", "libs", "c55-receipt", "new-output-dir"):
        ap.add_argument("--" + k, type=lambda s: Path(s).absolute(), required=True)
    ap.add_argument("--study", default="research/qualification-retake/packed_layer_service")
    for k in ("expect-head", "unit", "build-sha256", "input-sha256", "c55-sha256"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--in-scope", action="store_true", help=argparse.SUPPRESS)
    sys.exit(main(ap.parse_args()))
