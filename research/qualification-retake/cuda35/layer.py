"""Single bounded numerical C266 layer-35 bridge on the USB target file."""

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path

from vma_identity import Reference, same_vma, vma

CAP = 4 * 2**30
STOP = CAP - 512 * 2**20
SOURCE = Path(__file__).resolve().parent
RUN = "usb-c266-layer35-one-r3"
CUDA = "ff43655b15df5f3de1d5e00b0da18469a14f118bd644eb4b6d7f1915c85a4493"
EXE = "e198927ced892322ea3ba699e27022a1869bbfd263dcf607b42c6a8d291f9b92"


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text())


def shell(*args):
    return subprocess.check_output(args, text=True, timeout=8).strip()


def stat(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def driver_cuda_header(lines):
    match = re.search(r"CUDA(?: UMD)? Version:\s*([0-9]+\.[0-9]+)", lines)
    check(match is not None, "CUDA driver compatibility label absent")
    return match.group(1)


def run(repo, lab, model, out):
    out.mkdir()
    (out / "raw").mkdir()
    receipt = {
        "status": "NOT_RUN",
        "operator_calls": 0,
        "generation": 0,
        "protocol_sha256": sha(SOURCE / "protocolo.md"),
        "runner_sha256": sha(Path(__file__)),
    }
    proc = None
    fd_stack = ExitStack()
    observed = set()
    sample = cg = None
    try:
        sys.path.insert(0, str(repo / "tools"))
        import c118_start_inventory as inv
        import run_bounded as bounded
        from host_resource_policy import live_power

        def cg():
            state = bounded.cgroup_state()
            check(
                state
                and state["memory_max"] == state["memory_high"] == CAP
                and state["swap_max"] == state["swap_current"] == 0
                and state["memory_current"] < STOP
                and state["memory_peak"] < STOP,
                "cgroup caps, headroom or swap",
            )
            for key in ("events", "events_local"):
                check(
                    not any(state[key][k] for k in ("high", "max", "oom", "oom_kill")),
                    "cgroup limits event",
                )
            return {
                k: state[k]
                for k in (
                    "memory_max",
                    "memory_high",
                    "swap_max",
                    "memory_current",
                    "memory_peak",
                    "swap_current",
                    "events",
                    "events_local",
                )
            }

        receipt["cgroup_initial"] = cg()
        unit = repo / "research/qualification-retake"
        r266 = next((lab / "results").glob("c266-new-shape-native-*"))
        p = read(r266 / "protocol.json")
        policy = read(r266 / "resource-policy.json")
        check(
            p["resources"]["cgroup"]["memory_max_bytes"] == CAP
            and p["resources"]["cgroup"]["memory_stop_bytes"] == STOP,
            "C266 cap",
        )
        contract = read(unit / "elf-evidence/receipt.json")
        prior = read(unit / "host-evidence/receipt.json")
        frozen_at = dt.datetime.fromisoformat(prior["hash_started_utc"]).timestamp()
        receipt["model_sha256_previously_verified"] = prior["model_content"]["sha256"]
        check(
            receipt["model_sha256_previously_verified"] == p["model_sha256_previously_verified"]
            and p["model_sha256_previously_verified"].startswith("582bd40f68862001"),
            "target digest mismatch",
        )
        model = model.resolve(strict=True)
        initial_stat = stat(model)
        check(
            initial_stat[2] == prior["model_content"]["size_bytes"]
            and max(initial_stat[3:]) / 1e9 < frozen_at,
            "target stat changed after content audit",
        )
        mount = shell(
            "findmnt", "--first-only", "-n", "-o", "SOURCE,FSTYPE", "-T", str(model)
        ).split()
        check(len(mount) == 2 and mount[1] == "ext4", "target filesystem")
        parent = shell("lsblk", "-no", "PKNAME", mount[0])
        check(shell("lsblk", "-dn", "-o", "TRAN", "/dev/" + parent) == "usb", "target transport")
        receipt["host"] = {
            "cpu": next(
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "kernel": platform.release(),
            "mount": mount,
            "transport": "usb",
            "swaps_count": len(Path("/proc/swaps").read_text().splitlines()) - 1,
            "gpu": shell(
                "nvidia-smi",
                "--query-gpu=name,uuid,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ),
            "cuda_driver_compatibility_version": driver_cuda_header(shell("nvidia-smi")),
            "pressure": Path("/proc/pressure/memory").read_text().splitlines(),
            "nvme_mounts": shell("lsblk", "-dno", "NAME,SIZE,TRAN").splitlines(),
        }
        check(
            "620.70.06" in receipt["host"]["gpu"] and "8188" in receipt["host"]["gpu"],
            "GPU identity differs",
        )
        exe, _, capture, layer, device = p["runs"][-1]["command"]
        exe, capture = Path(exe), Path(capture)
        check((layer, device) == ("35", "cuda") and sha(exe) == EXE, "C266 executable")
        selected = {}
        for name, h in p["file_sha256"].items():
            f = Path(name)
            if (
                f == exe
                or f.suffix in (".cpp", ".h")
                or (f.parent == capture and (f.name == "result.json" or f.name.endswith("-35.bin")))
            ):
                check(sha(f) == h, "fixture/source mismatch: " + f.name)
                selected[f.name] = h
        check(len([n for n in selected if n.endswith("-35.bin")]) == 6, "incomplete capture")
        ordered = next((lab / "results").glob("c270-last-use-*/raw/c270-ordered.capture"))
        for name, h in selected.items():
            if name.endswith("-35.bin"):
                check(sha(ordered / name) == h, "C270 bridge changed: " + name)
        receipt["inputs"] = selected
        bindir = lab / "backends/c269-layer-last-use/build-c269-cuda/bin"
        rows = contract["selected_frozen_and_unpinned"]
        names = {
            r["load_name"]: r["resolved_sha256"]
            for r in rows
            if r["load_name"].startswith(
                ("libggml", "libllama.so", "libcuda.so", "libstdc++", "libgomp", "libgcc_s")
            )
        }
        check(len(names) == 9 and names["libggml-cuda.so.0"] == CUDA, "loader contract")
        env = os.environ.copy()
        check(
            not any(k.startswith(("LD_", "OMP_", "GOMP_", "KMP_")) for k in env),
            "unexpected loader or OpenMP override",
        )
        env["LD_LIBRARY_PATH"] = str(bindir)
        reference = {}
        for line in shell(
            "/lib64/ld-linux-x86-64.so.2", "--library-path", str(bindir), "--list", str(exe)
        ).splitlines():
            if " => " not in line:
                continue
            name, path = line.strip().split(" => ")
            if name in names:
                f = Path(path.split()[0]).resolve(strict=True)
                reference[name] = Reference(fd_stack, f, names[name])
        check(set(reference) == set(names), "incomplete expected loader map")
        receipt["resolved_elf_sha256"] = names
        by_path = {str(ref.path): name for name, ref in reference.items()}
        receipt["vma_verifier_sha256"] = sha(SOURCE / "vma_identity.py")
        power = {"source": "AC", "profile": "performance"}
        inv_args = dict(policy=policy, cap_bytes=CAP, expected_power=power)

        def sample(own_pid=None):
            ids = shell("nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits")
            check(not {int(i) for i in ids.splitlines()} - {own_pid}, "concurrent GPU compute")
            s = {
                "gpu": bounded.gpu_state(prospective=True),
                "thermal": bounded.thermal_state(prospective=True),
                "power": live_power(),
                "mem_available_bytes": bounded.mem_available(),
            }
            inv.validate_sample(s, **inv_args)
            return s

        (out / "raw" / "identity.json").write_text(json.dumps(initial_stat))
        prep = inv.collect(out, RUN, sample=sample, duration_s=60, **inv_args)
        inv.require_inventory(
            out, RUN, prep, duration_s=60, now=dt.datetime.now(dt.UTC), max_age_s=3, **inv_args
        )
        receipt["preflight"] = {k: v for k, v in prep.items() if k != "path"}
        check(stat(model) == initial_stat, "target changed during preflight")
        cg()
        print("ADMITTED one CUDA35 call after", prep["sample_count"], "samples", flush=True)
        since = time.monotonic()
        with (
            (out / "raw" / "stdout").open("xb") as stdout,
            (out / "raw" / "stderr").open("xb") as stderr,
        ):
            proc = subprocess.Popen(
                [str(exe), str(model), str(capture), layer, device],
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
            receipt["operator_calls"] = 1
            samples = []
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(sample, proc.pid)
                live_maps = Path(f"/proc/{proc.pid}/maps")
                while proc.poll() is None:
                    check(time.monotonic() - since < 60, "operator timeout")
                    cg()
                    try:
                        for line in live_maps.read_text().splitlines():
                            row = vma(line)
                            if row is None or row[3] not in by_path:
                                continue
                            name = by_path[row[3]]
                            same_vma(row[2], reference[name].key)
                            observed.add(name)
                    except (FileNotFoundError, ProcessLookupError):
                        check(proc.poll() is not None, "lost live process")
                    if pending.done():
                        samples.append(pending.result())
                        pending = pool.submit(sample, proc.pid)
                    time.sleep(0.01)
                samples.append(pending.result())
        receipt["mapped_elf"] = sorted(observed)
        receipt["live_samples"] = samples
        receipt["operator_exit_code"] = proc.returncode
        check(proc.returncode == 0, "operator failure; preserved stderr")
        check(observed == set(names), "missing live ELF mapping")
        for ref in reference.values():
            ref.verify()
        expected_lines = (r266 / "raw/c266-layer35.stdout").read_bytes()
        check(
            expected_lines == b"CANONICAL_R2_TILE first=0 n=1 bitwise=1 nonfinite=0 max_abs=0\n"
            b"PASS_NATIVE_CANONICAL_R2_LAYER layer=35 device=cuda "
            b"logical_bytes_read=54490112 O_DIRECT=1\n",
            "C266 historic result changed",
        )
        check((out / "raw/stdout").read_bytes() == expected_lines, "numerical result or byte scope")
        check(stat(model) == initial_stat, "target changed during run")
        receipt["stdout_sha256"] = sha(out / "raw/stdout")
        receipt["postflight"] = sample()
        receipt["cgroup_final"] = cg()
        receipt["status"] = "PASS_SINGLE_CUDA35_ROUTED_REFERENCE"
    except (
        OSError,
        KeyError,
        StopIteration,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        receipt["failure"] = f"{type(exc).__name__}: {exc}"
        receipt["status"] = "FAIL" if receipt["operator_calls"] else "NOT_RUN"
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        receipt["mapped_elf"] = sorted(observed)
        fd_stack.close()
        if proc is not None:
            receipt["operator_exit_code"] = proc.returncode
        if sample is not None and "postflight" not in receipt:
            try:
                receipt["postflight"] = sample()
                receipt["cgroup_final"] = cg()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                receipt["postflight_failure"] = str(exc)
        part = out / "receipt.json.part"
        part.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
        part.rename(out / "receipt.json")
    print(receipt["status"], receipt.get("failure", ""), flush=True)
    return int(not receipt["status"].startswith("PASS"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "lab", "model", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    opt = ap.parse_args()
    raise SystemExit(run(opt.repo, opt.lab, opt.model, opt.new_output_dir))
