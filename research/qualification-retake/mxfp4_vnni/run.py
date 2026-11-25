"""Supervise one preregistered MXFP4 CPU operator family in a private zero-swap scope."""

import argparse
import json
import os
import signal
import struct
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from decision import evaluate

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [str(HERE.parent / "nvme_admission/io_pair"), str(HERE.parent / "cuda35")]
import run as io  # noqa: E402
from c118_start_inventory import collect, require_inventory  # noqa: E402
from vma_identity import Reference, same_vma, vma  # noqa: E402

CAP = 2**30
STOP = 896 * 2**20
BASE = "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539"
R0 = "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313"
POWER = {"source": "AC", "profile": "performance"}
RUN_ID = "cpu-mxfp4-vnni"
require = io.require


def scope():
    c = io.cgroup_state()
    require(
        c
        and (c["memory_high"], c["memory_max"], c["swap_max"], c["swap_current"])
        == (CAP, CAP, 0, 0),
        "1 GiB high/max, zero swap required",
    )
    require(
        c["memory_peak"] < STOP
        and not any(c["events_local"][k] for k in ("high", "max", "oom", "oom_kill")),
        "cgroup resource stop",
    )
    return c


def observed(policy):
    c = scope()
    require(not io.concurrent(), "competing workload")
    obs = io.live_sample()
    io.validate_sample(obs, policy=policy, cap_bytes=CAP, expected_power=POWER)
    psi = io.host_pressure()
    require(
        psi < 10 and obs["thermal"]["cpu_tctl_c"] < policy["cpu"]["warning_c"],
        "PSI or CPU thermal guard",
    )
    warning = policy["gpu"]["warning_c"]
    require(warning is None or obs["gpu"]["temperature_c"] < warning, "GPU thermal guard")
    for disk in policy["nvme"]:
        temp = obs["thermal"]["nvme_composite_by_sensor"][disk["sensor"]]
        require(disk["warning_c"] is None or temp < disk["warning_c"], "NVMe thermal guard")
    obs.update(
        psi_full_avg10=psi,
        cgroup_current_bytes=c["memory_current"],
        cgroup_peak_bytes=c["memory_peak"],
    )
    return obs


def package_energy():
    p = Path("/sys/class/powercap/intel-rapl:0")
    try:
        return int((p / "energy_uj").read_text()), int((p / "max_energy_range_uj").read_text())
    except (OSError, ValueError):
        return None


def measured_child(argv, tag, env, root, policy, report, telemetry):
    begin, energy = time.monotonic(), package_energy()
    with (root / f"{tag}.stdout").open("xb") as out, (root / f"{tag}.stderr").open("xb") as err:
        rss_out = root / f"{tag}.rss"
        command = ["/usr/bin/time", "-f", "%M", "-o", str(rss_out), *argv]
        proc = subprocess.Popen(command, stdout=out, stderr=err, env=env, start_new_session=True)
        try:
            while True:
                sample = observed(policy)
                telemetry.write(
                    json.dumps(dict(stage=tag, monotonic_s=time.monotonic(), observation=sample))
                    + "\n"
                )
                telemetry.flush()
                try:
                    code = proc.wait(timeout=0.65)
                    break
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
    after = package_energy()
    elapsed = time.monotonic() - begin
    delta = None
    if energy and after and energy[1] == after[1] and energy[1] > 0:
        delta = ((after[0] - energy[0]) % energy[1]) / 1e6
    report["children"][tag] = dict(
        returncode=code,
        wall_s=elapsed,
        package_energy_j=delta,
        package_mean_power_w=delta / elapsed if delta is not None else None,
        max_rss_kib=int(rss_out.read_text().splitlines()[-1]),
        stdout_sha256=io.sha256(root / f"{tag}.stdout"),
        stderr_sha256=io.sha256(root / f"{tag}.stderr"),
    )
    require(code == 0, f"{tag} failed; see preserved stderr")
    observed(policy)


def tsv(path):
    lines = path.read_text().splitlines()
    require(len(lines) >= 2, "missing rows: " + path.name)
    hdr = lines[0].split()
    require(len(hdr) == len(set(hdr)), "duplicate field")
    return [dict(zip(hdr, line.split(), strict=True)) for line in lines[1:]]


def cache_inventory():
    out = {}
    cpuinfo = Path("/proc/cpuinfo").read_text()
    require("AMD Ryzen AI 9 HX 370" in cpuinfo and "avx_vnni" in cpuinfo, "processor/ISA")
    for cpu in (0, 4):
        require(cpu in os.sched_getaffinity(0), "timing CPU missing from scope")
        cpu_path = Path(f"/sys/devices/system/cpu/cpu{cpu}")
        rows = []
        for c in sorted((cpu_path / "cache").glob("index*")):
            rows.append(
                {
                    k: (c / k).read_text().strip()
                    for k in ("level", "type", "size", "shared_cpu_list")
                }
            )
        require(any(x["level"] == "3" for x in rows), "cache inventory incomplete")
        out[str(cpu)] = dict(
            cache=rows,
            sibling_list=(cpu_path / "topology/thread_siblings_list").read_text().strip(),
        )
    return out


def verified_maps(data, refs):
    pending = set(refs)
    names = {r.path.name for r in refs.values()}
    addresses = set()
    for line in data.splitlines():
        row = vma(line)
        if row is None:
            continue
        _, _, key, name = row
        require("(deleted)" not in name, "deleted mapped image")
        path = Path(name)
        require(
            not path.name.startswith(("libggml-cuda", "libcuda.so", "libcudart")),
            "GPU runtime loaded",
        )
        owners = [label for label, r in refs.items() if name == str(r.path)]
        if owners:
            (label,) = owners
            same_vma(key, refs[label].key)
            pending.discard(label)
            if "x" in line.split()[1]:
                addresses.add(label)
        elif path.name in names or path.name.startswith(("libggml-cpu.so", "libggml-base.so")):
            raise ValueError("another copy of an expected ELF was mapped")
    require(not pending and addresses == set(refs), "missing matching executable VMA")
    for ref in refs.values():
        ref.verify()
    return {label: r.digest for label, r in refs.items()}


def summary(path):
    rows = [json.loads(line)["observation"] for line in path.read_text().splitlines()]
    if not rows:
        return dict(sample_count=0)
    return dict(
        sample_count=len(rows),
        cpu_tctl_max_c=max(r["thermal"]["cpu_tctl_c"] for r in rows),
        gpu_max_c=max(r["gpu"]["temperature_c"] for r in rows),
        gpu_max_mib=max(r["gpu"]["used_mib"] for r in rows),
        gpu_max_power_w=max(r["gpu"]["power_w"] for r in rows),
        nvme_max_c=max(t for r in rows for t in r["thermal"]["nvme_composite_by_sensor"].values()),
        psi_full_avg10_max=max(r["psi_full_avg10"] for r in rows),
        host_mem_available_min_bytes=min(r["mem_available_bytes"] for r in rows),
        cgroup_peak_bytes=max(r["cgroup_peak_bytes"] for r in rows),
        power_sources=sorted({r["power"]["source"] for r in rows}),
        power_profiles=sorted({r["power"]["profile"] for r in rows}),
    )


def execute(a, report):
    root = a.new_output_dir
    raw = root / "raw"
    raw.mkdir()
    commit, tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    require(
        len(a.commit) == 40
        and commit == a.commit
        and not subprocess.check_output(["git", "-C", REPO, "status", "--porcelain"]),
        "clean frozen commit required",
    )
    report.update(
        commit=commit,
        tree=tree,
        protocol_sha256=io.sha256(HERE / "protocol.md"),
        cpu_cache=cache_inventory(),
        signal="single-thread routed gate and up operand only",
    )
    require(io.sha256(a.placement) == io.PLACEMENT_SHA, "NVMe placement receipt")
    place = json.loads(a.placement.read_text())
    path = Path(place["working_copy"]).resolve(strict=True)
    ident = io.stat_id(path)
    require(
        place["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and place["source_sha256"] == place["destination_direct_reread"]["sha256"] == io.TARGET
        and ident[2] == 63_387_346_208
        and ident[4] <= a.placement.stat().st_mtime_ns,
        "GGUF post-digest identity",
    )
    io.disk(path, "nvme")
    policy = json.loads(a.policy.read_text())
    require(
        policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "C55 derived policy/admission",
    )
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    require(0 <= age <= 3600, "same-hour C55 required")
    build = a.build_dir.resolve(strict=True)
    require(io.sha256(build / "build.json") == a.build_sha256, "frozen build receipt")
    frozen = json.loads((build / "build.json").read_text())
    require(
        frozen["status"] == "PASS_BUILD_DISASSEMBLY_ONLY"
        and frozen["r0"]["sha256"] == R0
        and frozen["symbol"] == "ggml_vec_dot_mxfp4_q8_0",
        "operator contracts",
    )
    report.update(
        build_receipt_sha256=a.build_sha256,
        clockbench_sha256=a.clockbench_sha256,
        abi_symbol=frozen["symbol"],
        gcc_sha256=frozen["gcc_sha256"],
        c55_policy_sha256=io.sha256(a.policy),
        placement_receipt_sha256=io.PLACEMENT_SHA,
        c55_age_s_at_admission=age,
        target_sha256=io.TARGET,
    )
    bindir = a.lab.resolve(strict=True) / "backends/c269-layer-last-use/build-c269-cuda/bin"
    lib = {
        "r0": (bindir / "libggml-cpu.so.0.15.3", R0),
        "base": (bindir / "libggml-base.so.0.15.3", BASE),
        "clockbench": (a.clockbench.resolve(strict=True), a.clockbench_sha256),
    }
    for name in ("control", "candidate", "fallback"):
        lib[name] = (build / (name + ".so"), frozen["arms"][name]["sha256"])
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "HOME": str(root),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MALLOC_ARENA_MAX": "2",
        "LD_LIBRARY_PATH": str(bindir),
    }
    with ExitStack() as stack:
        refs = {k: Reference(stack, p, h) for k, (p, h) in lib.items()}
        require(len({r.key for r in refs.values()}) == len(refs), "duplicate ELF identity")
        report["frozen_elf_sha256"] = {k: r.digest for k, r in refs.items()}
        conditions = dict(policy=policy, cap_bytes=CAP, expected_power=POWER)
        inv = collect(root, RUN_ID, **conditions, sample=lambda: observed(policy))
        io.save(root / "c118.json", inv)
        report["inventory"] = {k: v for k, v in inv.items() if k != "path"}
        report["c118_summary"] = summary(raw / (RUN_ID + ".start-inventory.jsonl"))
        source = root / "inputs"
        native = root / "native"
        native.mkdir()
        with (raw / "telemetry.jsonl").open("x") as log:
            require_inventory(root, RUN_ID, inv, **conditions, max_age_s=3)
            measured_child(
                [
                    sys.executable,
                    "-B",
                    str(HERE / "inputs.py"),
                    "--lab",
                    str(a.lab),
                    "--model",
                    str(path),
                    "--new-output-dir",
                    str(source),
                ],
                "inputs",
                env,
                raw,
                policy,
                report,
                log,
            )
            inp = json.loads((source / "inputs.json").read_text())
            require(
                inp["status"] == "PASS_AUTHENTICATED_OPERATOR_INPUTS"
                and inp["weight_bytes"] == 35_251_200
                and inp["activation_sha256"]
                == "cdba177b2040d9ea5672e29e18bb8ac95203a44ac45085c57bc791b73ebd2344"
                and io.stat_id(path) == ident,
                "authenticated inputs",
            )
            report["inputs"] = inp
            cmd = [lib[k][0] for k in ("clockbench", "r0", "control", "candidate", "fallback")]
            measured_child(
                [*cmd, source / "weights.bin", source / "activation.f32", native],
                "operator",
                env,
                raw,
                policy,
                report,
                log,
            )
        report["mapped_elf_sha256"] = verified_maps((native / "maps.tsv").read_text(), refs)
    (parity,) = tsv(native / "parity.tsv")
    require(
        {k: int(v) for k, v in parity.items()}
        == {"real_rows": 23040, "synthetic_rows": 160, "quant_bytes": 3060},
        "incomplete parity population",
    )
    require(
        (native / "gold.f32").stat().st_size == 23040 * 4
        and (native / "activation.q8").stat().st_size == 3060,
        "invalid operator artifacts",
    )
    arms = tsv(native / "arms.tsv")
    for arm in arms:
        for key in ("cpu", "arm", "rows", "repeats", "duration_ns"):
            arm[key] = int(arm[key])
    nonfinite = any(
        bits & 0x7F800000 == 0x7F800000
        for (bits,) in struct.iter_unpack("<I", (native / "gold.f32").read_bytes())
    )
    require(not nonfinite, "nonfinite R0 gold")
    report.update(
        evaluate(arms),
        parity={k: int(v) for k, v in parity.items()},
        arms=arms,
        cgroup_peak_bytes=scope()["memory_peak"],
        run_summary=summary(raw / "telemetry.jsonl"),
        artifacts_sha256={p.name: io.sha256(p) for p in sorted(native.iterdir()) if p.is_file()},
    )
    require(
        sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) < 199 * 2**20,
        "artifact budget",
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("lab", "placement", "policy", "build-dir", "clockbench", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    for name in ("build-sha256", "clockbench-sha256", "commit"):
        cli.add_argument("--" + name, required=True)
    a = cli.parse_args()
    a.new_output_dir = a.new_output_dir.resolve()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    report = {
        "schema": "mxfp4-vnni-supervised-operator-v1",
        "decision": "FAIL_PRESERVED",
        "children": {},
        "model_forwards": 0,
        "gpu_compute": 0,
    }
    started = time.monotonic()

    def expired(*_):
        raise TimeoutError("300 s family limit")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(300)
    try:
        execute(a, report)
    except Exception as error:
        report["decision"] = "FAIL_PRESERVED"
        report["reason"] = f"{type(error).__name__}: {error}"
        for path in (a.new_output_dir, a.clockbench.parent, a.build_dir, a.lab):
            report["reason"] = report["reason"].replace(str(path), "<private>")
        for name in ("parity.tsv", "arms.tsv"):
            p = a.new_output_dir / "native" / name
            if p.exists():
                report[name + "_preserved_sha256"] = io.sha256(p)
    finally:
        signal.alarm(0)
    report["family_wall_s"] = time.monotonic() - started
    pending = a.new_output_dir / ".receipt.pending"
    io.save(pending, report)
    pending.rename(a.new_output_dir / "receipt.json")
    print(report["decision"])
    return int(report["decision"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
