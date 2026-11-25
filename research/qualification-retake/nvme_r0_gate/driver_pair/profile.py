"""Run the sealed synthetic mixed CUDA fixture with a private, authenticated driver."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SELF = Path(__file__).resolve()
Q = Path("research/qualification-retake")
S = Q / "nvme_r0_gate/driver_pair"
MIB = 1 << 20
CAP = 1024 * MIB
STATIC_CAP = 2 * CAP
MAX_READ = 1536 * MIB
MAX_OUT = 32 * MIB
PASS = "PASS_C269_MIXED_KERNEL_WITH_R0_DRIVER_ONLY"
MIXED = "d931bbe373b162633d278da98fac60352e0dd15abd6ed75acfcedacc5fa802c7"
PINS = {
    S / "mixed_protocol.md": "57931562b37cb3887f91facf0ed9225e4540763e11d5574b1f1ee9eb2ab2631e",
    S / "receipt.json": "80af38c44b1128b64dac31342c508633d8331bb7f544eaedeac7a7b346d48292",
    Q
    / "nvme_r0_gate/inputs/receipt.json": "29795e9d68452efb6e0dea1df9e873b27fcf1011d36b899abd52bfdd91ce2a8e",  # noqa: E501
    Q
    / "packed_cpu_mixed/receipts/v3-r02-native.json": "633f12763a9eeeddf13935196efabc6d5c09a5578d7887b0e49874442ec8079d",  # noqa: E501
    Q
    / "packed_cpu_mixed/run.py": "5c09ae1cc964859c7076231d0a2e71061f056f8b7e1ae01a46835f8fb46b6181",
    Q
    / "packed_layer_service/profile.py": "ae3e5a752d68ad0187eba0e9329e1e03fcb9e429fe5367c6f5a4258e626cf7bb",  # noqa: E501
    Q
    / "packed_real_layer/profile.py": "3dfc12a50909fddd285143023a2edff5cd6e25b087453f21d4950649618db7cb",  # noqa: E501
}
DRIVER = "libcuda.so.620.70.06"
TOOLKIT = ("libcudart.so.13.3.29", "libcublas.so.13.6.0.2", "libcublasLt.so.13.6.0.2")


def need(test, why):
    if not test:
        raise ValueError(why)


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def token(s):
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def remember(path, records):
    path = path.resolve(strict=True)
    key = str(path)
    with path.open("rb") as f:
        st = token(os.fstat(f.fileno()))
        existing = next((v for v in records.values() if v["stat"][:2] == st[:2]), None)
        if existing:
            need(existing["stat"] == st, "identity changed: " + path.name)
            sha = existing["sha256"]
        else:
            used = sum({tuple(v["stat"][:2]): v["stat"][2] for v in records.values()}.values())
            need(used + st[2] <= MAX_READ, "static read budget")
            sha = hashlib.file_digest(f, "sha256").hexdigest()
        need(st == token(os.fstat(f.fileno())) == token(path.stat()), "changing open descriptor")
    records[key] = {"stat": st, "sha256": sha}
    return sha


def check_records(records):
    for name, row in records.items():
        need(
            token(Path(name).stat()) == row["stat"], "changed authenticated ELF: " + Path(name).name
        )


def dependency_paths(text):
    paths = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("linux-vdso.so."):
            continue
        match = re.fullmatch(r"(?:(\S+) => )?(/.+?)\s+\(0x[0-9a-fA-F]+\)", line)
        need(match is not None, "unknown or missing loader dependency: " + line)
        path = Path(match[2])
        name = match[1] or path.name
        need(name not in paths, "duplicate SONAME " + name)
        paths[name] = str(path)
    need(paths, "empty dependency map")
    return paths


def initialized(text, pid):
    paths = set()
    for line in text.splitlines():
        if "calling init:" in line:
            match = re.fullmatch(r"\s*(\d+):\s+calling init:\s*(/.+?)\s*", line)
            need(match and int(match[1]) == pid, "unknown loader init line or pid")
            paths.add(str(Path(match[2]).resolve(strict=True)))
    need(paths, "missing loader init")
    return paths


def required_present(actual, required):
    missing = set(required) - actual
    need(
        not missing, "missing runtime providers: " + ",".join(sorted(Path(x).name for x in missing))
    )


def output_bytes(path):
    return sum(f.lstat().st_size for f in path.rglob("*") if f.is_file() or f.is_symlink())


def get_json(path):
    return json.loads(path.read_bytes())


def save(path, obj):
    tmp = path.with_suffix(".pending")
    with tmp.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    os.link(tmp, path)
    tmp.unlink()


def git(a, *args):
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-C", a.checkout, *args], text=True, timeout=12
    ).strip()


def source_guard(a):
    head = git(a, "rev-parse", "HEAD")
    need(re.fullmatch("[a-f0-9]{40}", a.expect_head) and head == a.expect_head, "checkout HEAD")
    need(not git(a, "status", "--porcelain"), "dirty checkout")
    git(a, "ls-files", "--error-unmatch", str(SELF.relative_to(a.checkout)))
    need(SELF.parent == (a.checkout / S).resolve(), "execute the committed supervisor")
    for name, sha in PINS.items():
        need(digest(a.checkout / name) == sha, "source/receipt " + str(name))
    return {
        "head": head,
        "tree": git(a, "rev-parse", "HEAD^{tree}"),
        "supervisor_sha256": digest(SELF),
        "protocol_sha256": PINS[S / "mixed_protocol.md"],
    }


def native_env(a, *, debug=False):
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "CUDA_VISIBLE_DEVICES": "0",
        "CUDA_CACHE_DISABLE": "1",
        "OMP_NUM_THREADS": "2",
        "OMP_DYNAMIC": "FALSE",
        "LD_LIBRARY_PATH": str(a.libs) + ":" + str(a.new_output_dir / "driver"),
    }
    if debug:
        env.update(LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(a.new_output_dir / "loads"))
    return env


def alias_check(a):
    folder = a.new_output_dir / "driver"
    alias = folder / "libcuda.so.1"
    need(
        {p.name for p in folder.iterdir()} == {alias.name}
        and alias.is_symlink()
        and alias.resolve(strict=True) == a.installed_driver.resolve(strict=True),
        "private driver alias",
    )
    return alias


def scope_check(bounded, unit, limit):
    cg = bounded.cgroup_state()
    need(
        cg
        and cg["path"].endswith("/" + unit + ".scope")
        and cg["memory_max"] == limit
        and cg["swap_max"] == cg["swap_current"] == 0,
        "scope identity or resource limits",
    )
    return cg


def c55(a, p, policy):
    data = p.sealed_json(a.c55_receipt, a.c55_sha256)
    pol = p.sealed_json(
        a.c55_receipt.parent / "resource-policy.json", data["canonical_policy_sha256"]
    )
    p.sealed_file(a.c55_receipt.parent / "samples.jsonl", data["window_sha256"])
    for name, key in (("window.py", "runner_sha256"), ("protocolo.md", "protocol_sha256")):
        p.sealed_file(a.checkout / Q / "nvme_admission" / name, data[key])
    need(
        data["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not data["reason"]
        and data["span_s"] >= 60
        and data["gpu_driver"] == "620.70.06"
        and pol == policy.derive_policy(snapshot=pol["snapshot"])
        and min(
            v["cap_max_bytes"] for v in (data["canonical_memory"], data["memory"], pol["memory"])
        )
        >= STATIC_CAP,
        "C55 resources",
    )
    return pol


def prepare(a, report, p):
    root = a.new_output_dir
    original = get_json(a.checkout / Q / "packed_cpu_mixed/receipts/v3-r02-native.json")
    historical = get_json(a.checkout / Q / "nvme_r0_gate/inputs/receipt.json")["startup_dso_sha256"]
    need(
        a.installed_driver.resolve(strict=True).name == DRIVER
        and a.executable.stat().st_size == 81192
        and original["executable_sha256"] == MIXED,
        "driver or executable",
    )
    monitor = Path(os.environ["LD_LIBRARY_PATH"]) / "libnvidia-ml.so.1"
    need(
        monitor.resolve(strict=True).parent == a.installed_driver.resolve(strict=True).parent,
        "driver not from qualified NVML directory",
    )
    (root / "driver").mkdir()
    (root / "driver/libcuda.so.1").symlink_to(a.installed_driver.resolve(strict=True))
    alias = alias_check(a)
    files = {}
    need(remember(a.executable, files) == MIXED, "wrong executable")
    loader = Path("/lib64/ld-linux-x86-64.so.2")
    listed = subprocess.check_output(
        [loader, "--list", a.executable], text=True, env=native_env(a), timeout=8
    )
    links = dependency_paths(listed)
    required = {}
    for name in (*TOOLKIT, DRIVER):
        required[name] = historical[name]
    required.update(original["providers_sha256"])
    crypto = Path("/usr/lib64/libcrypto.so.3").resolve(strict=True)
    required[crypto.name] = original["hash_provider_sha256"]
    paths = [Path(s).resolve(strict=True) for s in links.values()]
    actual = {}
    for f in set([*paths, alias.resolve(strict=True)]):
        need(f.name not in actual, "ambiguous resolved basename")
        sha = remember(f, files)
        actual[f.name] = str(f)
        if f.name in required:
            need(sha == required[f.name], "critical digest: " + f.name)
    need(
        set(required) <= actual.keys()
        and all((a.libs / name).samefile(actual[name]) for name in original["providers_sha256"])
        and Path(actual[crypto.name]).samefile(crypto),
        "critical preflight coverage",
    )
    for soname, filename in links.items():
        if soname.startswith("libcuda.so."):
            need(Path(filename).samefile(alias), "incorrect driver in linker map")
    private = dict(
        files=files,
        links={s: [f, str(Path(f).resolve(strict=True))] for s, f in links.items()},
        required=[actual[n] for n in required],
    )
    save(root / "static-map.json", private)
    report.update(
        static_sha256=digest(root / "static-map.json"),
        executable_sha256=MIXED,
        required_sha256=required,
    )
    check_records(files)


def pids():
    lines = subprocess.check_output(
        ["/usr/bin/nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        text=True,
        timeout=3,
    ).split()
    return [int(n) for n in lines]


def physical(a, r, p, service, b, policy, inv, guard0):
    out = a.new_output_dir
    inventory = get_json(out / "static-map.json")
    pol = c55(a, p, policy)
    limits = policy.freeze_protocol_resource_limits(
        pol, cgroup_memory_max_bytes=CAP, start_mode="CAPACITY_ADMISSION_START"
    )
    need(limits["cgroup"]["memory_stop_bytes"] == CAP // 2, "preventive memory margin")
    proto = dict(resources=limits, limits={})
    guard = policy.RuntimeGuard(proto, guard0)
    r["monitor_provider"], unchanged = service.monitor_provider(p)
    need(r["monitor_provider"]["mode"] == "PRIVATE_MATCHED_NVML", "qualified private monitor")
    raw = out / "raw"
    raw.mkdir()
    (out / "native").mkdir()
    args = dict(
        policy=pol,
        cap_bytes=CAP,
        expected_power={n: pol["power"][n] for n in ("source", "profile")},
        duration_s=60,
    )
    cfg = inv.collect(out, a.unit, **args)
    r["c118"] = {k: v for k, v in cfg.items() if k != "path"}
    obs = inv.live_sample()
    reasons = policy.validate_start_observation(
        proto,
        available_bytes=obs["mem_available_bytes"],
        gpu=obs["gpu"],
        thermal=obs["thermal"],
        power=obs["power"],
        psi_full_avg10=policy.host_pressure(),
    )
    need(not reasons, "start guard " + str(reasons))
    started = time.monotonic()
    last = started

    def sample(stream, allowed_pid=None):
        nonlocal last
        compute = pids()
        cg = b.cgroup_state()
        if compute:
            need(allowed_pid is not None and set(compute) == {allowed_pid}, "foreign compute PID")
            # If the child disappeared in the query race, its Popen PID already identifies it.
            membership = Path("/proc") / str(allowed_pid) / "cgroup"
            if membership.exists():
                try:
                    need(
                        "0::" + cg["path"] in membership.read_text().splitlines(), "foreign cgroup"
                    )
                except FileNotFoundError:
                    pass
        row = dict(
            utc=dt.datetime.now(dt.UTC).isoformat(),
            cgroup=cg,
            proc=b.proc_status(os.getpid()),
            proc_owner="supervisor",
            compute_pids=compute,
            gpu=b.gpu_state(prospective=True),
            thermal=b.thermal_state(prospective=True),
            mem_available_bytes=b.mem_available(),
            resource_observation=dict(
                power=policy.live_power(), host_psi_full_avg10=policy.host_pressure()
            ),
        )
        now = time.monotonic()
        row.update(elapsed_s=now - started, gap_s=now - last)
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        last = now
        r["sample_count"] = r.get("sample_count", 0) + 1
        reason = guard.check(row)
        need(not reason and row["gap_s"] <= 3, "runtime guard: " + str(reason or "cadence"))
        need(output_bytes(out) < MAX_OUT, "private output limit")

    proc = None
    with (out / "telemetry.jsonl").open("x") as monitor:
        try:
            sample(monitor)
            check_records(inventory["files"])
            alias_check(a)
            unchanged()
            inv.require_inventory(out, a.unit, cfg, max_age_s=3, **args)
            birth = time.monotonic()
            with (out / "stdout.txt").open("xb") as so, (out / "stderr.txt").open("xb") as se:
                proc = subprocess.Popen(
                    [a.executable, out / "native"],
                    stdout=so,
                    stderr=se,
                    env=native_env(a, debug=True),
                    start_new_session=True,
                )
                r["native_pid"] = proc.pid
                while proc.poll() is None:
                    sample(monitor, proc.pid)
                    need(time.monotonic() - birth < 150, "native wall")
                    try:
                        proc.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        pass
                r["rc"] = proc.returncode
            r["native_supervised_wall_s"] = time.monotonic() - birth
            need(proc.returncode == 0, "native exit")
        finally:
            if proc and proc.poll() is None:
                b.stop_own_group(proc)
            sample(monitor)
            unchanged()
    mixed = load(a.checkout / Q / "packed_cpu_mixed/run.py", "mixed_numeric_v3")
    v3 = get_json(a.checkout / Q / "packed_cpu_mixed/receipts/v3-r02-native.json")
    scopes = {str(k): v for k, v in mixed.verify_native(out, a.libs).items()}
    need(
        scopes == v3["scopes"]
        and digest(out / "native/boundary.tsv") == v3["boundary_journal_sha256"],
        "V3 R02 exact replay",
    )
    check_records(inventory["files"])
    alias_check(a)
    r.update(
        outputs_sha256={k: v["result_sha256"] for k, v in scopes.items()},
        journal_sha256=v3["boundary_journal_sha256"],
        telemetry_sha256=digest(out / "telemetry.jsonl"),
        cgroup_end=b.cgroup_state(),
        clean_compute_pids=pids(),
    )
    need(not r["clean_compute_pids"], "compute cleanup")


def post(a, r):
    out = a.new_output_dir
    inventory = get_json(out / "static-map.json")
    measured = get_json(out / "run.json")
    pid = measured["native_pid"]
    log = out / f"loads.{pid}"
    loaded = initialized(log.read_text(), pid)
    required_present(loaded, inventory["required"])
    records = inventory["files"]
    check_records(records)
    alias_check(a)
    # Recheck SONAME aliases as well as their originally resolved target identities.
    for source, resolved in inventory["links"].values():
        need(
            str(Path(source).resolve(strict=True)) == resolved and resolved in records,
            "changed loader alias",
        )
    initial = set(records)
    for name in sorted(loaded - initial):
        remember(Path(name), records)
    optional = {}
    for name in sorted(loaded - initial):
        short = Path(name).name
        optional[short] = records[name]["sha256"]
    startup = get_json(a.checkout / Q / "nvme_r0_gate/inputs/receipt.json")["startup_dso_sha256"]
    public = {
        Path(n).name: row["sha256"]
        for n, row in records.items()
        if n != str(a.executable.resolve())
    }
    need(
        len(public) == len([n for n in records if n != str(a.executable.resolve())]),
        "duplicate provider basename",
    )
    comparison = {
        n: dict(actual=public.get(n), r0=s, equal=public[n] == s if n in public else None)
        for n, s in startup.items()
    }
    r.update(
        loaded_init_sha256={Path(n).name: records[n]["sha256"] for n in sorted(loaded)},
        optional_dl_init_sha256=optional,
        loader_log_sha256=digest(log),
        comparison_with_r0=comparison,
        all_current_elfs=public,
        static_unique_elf_bytes=sum(
            {tuple(row["stat"][:2]): row["stat"][2] for row in records.values()}.values()
        ),
    )
    check_records(records)
    need(output_bytes(out) + 65536 < MAX_OUT, "private output closure")
    for name in public:
        if name.startswith("libnvidia-"):
            need(name.endswith(".620.70.06"), "unqualified auxiliary NVIDIA release: " + name)


def scoped(a, r):
    q = a.checkout / Q
    p = load(q / "packed_real_layer/profile.py", "prior_layer_resources")
    s = load(q / "packed_layer_service/profile.py", "prior_nvml")
    sys.path.insert(0, str(a.checkout / "tools"))
    import c118_start_inventory as inv
    import host_resource_policy as policy
    import run_bounded as b

    unit = a.unit if a.phase == "run" else a.unit + "-" + a.phase
    baseline = scope_check(b, unit, CAP if a.phase == "run" else STATIC_CAP)
    if a.phase == "pre":
        c55(a, p, policy)
        prepare(a, r, p)
    elif a.phase == "run":
        physical(a, r, p, s, b, policy, inv, baseline)
    else:
        post(a, r)
    r["cgroup_final"] = b.cgroup_state()


def main(a):
    os.umask(0o077)
    out = a.new_output_dir
    if not a.phase:
        out.mkdir(mode=0o700, exist_ok=False)
    start = time.monotonic()
    r = {"status": "FAIL_PRESERVED", "phase": a.phase or "campaign", "c55_sha256": a.c55_sha256}
    try:
        r.update(source_guard(a))
        need(re.fullmatch(r"tesy-[a-z0-9][a-z0-9-]{1,100}", a.unit), "unit")
        if a.phase:
            scoped(a, r)
            r["status"] = "PASS_" + a.phase.upper()
        else:
            r["phases"] = {}
            static_s = 0
            for phase in ("pre", "run", "post"):
                limit = 240 if phase == "run" else 60 - static_s
                need(limit >= 1, "combined static wall budget")
                unit = a.unit if phase == "run" else a.unit + "-" + phase
                cap = CAP if phase == "run" else STATIC_CAP
                command = [
                    "/usr/bin/systemd-run",
                    "--user",
                    "--scope",
                    "--quiet",
                    "--collect",
                    "--unit=" + unit,
                    "-p",
                    f"MemoryMax={cap}",
                    "-p",
                    "MemorySwapMax=0",
                    "-p",
                    f"RuntimeMaxSec={int(limit)}s",
                    "-p",
                    "CPUAccounting=yes",
                    "-p",
                    "IOAccounting=yes",
                    sys.executable,
                    "-I",
                    "-B",
                    str(SELF),
                    *sys.argv[1:],
                    "--phase",
                    phase,
                ]
                t = time.monotonic()
                with (
                    (out / (phase + ".stdout")).open("xb") as so,
                    (out / (phase + ".stderr")).open("xb") as se,
                ):
                    code = subprocess.run(
                        command, stdout=so, stderr=se, timeout=limit + 2
                    ).returncode
                elapsed = time.monotonic() - t
                if phase != "run":
                    static_s += elapsed
                rec = get_json(out / (phase + ".json"))
                if "cgroup_final" in rec:
                    cg = Path("/sys/fs/cgroup") / rec["cgroup_final"]["path"].lstrip("/")
                    # A scope may briefly remain while systemd collects it.
                    for _ in range(20):
                        try:
                            members = (cg / "cgroup.procs").read_text().strip()
                        except FileNotFoundError:
                            members = ""
                        if not members:
                            break
                        time.sleep(0.05)
                    need(not members, "scope not drained: " + phase)
                r["phases"][phase] = {
                    "receipt_sha256": digest(out / (phase + ".json")),
                    "status": rec["status"],
                    "wall_s": elapsed,
                    "rc": code,
                }
                need(
                    code == 0 and elapsed <= limit and rec["status"] == "PASS_" + phase.upper(),
                    phase + " failed: " + str(rec.get("reason", "scope")),
                )
            r["status"] = PASS
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        r.update(closed_utc=dt.datetime.now(dt.UTC).isoformat(), wall_s=time.monotonic() - start)
        save(out / ((a.phase or "receipt") + ".json"), r)
    return int(r["status"].startswith("FAIL"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in (
        "checkout",
        "executable",
        "libs",
        "installed-driver",
        "c55-receipt",
        "new-output-dir",
    ):
        ap.add_argument("--" + key, type=lambda s: Path(s).absolute(), required=True)
    for key in ("c55-sha256", "expect-head", "unit"):
        ap.add_argument("--" + key, required=True)
    ap.add_argument("--phase", choices=["pre", "run", "post"], help=argparse.SUPPRESS)
    sys.exit(main(ap.parse_args()))
