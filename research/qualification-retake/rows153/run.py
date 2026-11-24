"""Run C266's CPU0 and CUDA25 selected 153-row operators under the R3 VMA guard."""

import argparse
import datetime as dt
import json
import os
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = [
    (0, "cpu", 67, 889476992, "aa71877afd1ce43f1f56988105af75021d649fe842ae47d39402c3a06b0fe5bf"),
    (25, "cuda", 54, 717178112, "c4e3740f2aabb51efc9d9e7c96d9bd8f884022f3d856184f494d47cc3003249a"),
]
CAP = 4 * 2**30


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def prepare(pins, camp, lab, layer, device, expected_count, nbytes, stdout_sha, common):
    arm = next(a for a in pins["runs"] if a["command"][-2:] == [str(layer), device])
    exe, _, capture, *_ = arm["command"]
    exe, capture = Path(exe), Path(capture)
    check(common.sha(exe) == common.EXE, "C266 executable changed")
    ordered = next(lab.glob("results/c270-last-use-*/raw/c270-ordered.capture"))
    hashes = {}
    for name, h in pins["file_sha256"].items():
        f = Path(name)
        if f.parent == capture and f.name.endswith(f"-{layer}.bin"):
            check(common.sha(f) == common.sha(ordered / f.name) == h, "gold differs: " + f.name)
            hashes[f.name] = h
        elif (f.parent == capture and f.name == "result.json") or f.suffix in (".cpp", ".h"):
            check(common.sha(f) == h, "source or capture manifest changed")
    check(len(hashes) == 6, "missing layer capture")
    ids = list(struct.iter_unpack("<iiii", (capture / f"ffn_moe_topk-{layer}.bin").read_bytes()))
    unique = set().union(*map(set, ids))
    check(
        len(ids) == 153
        and all(len(set(frame)) == 4 for frame in ids)
        and len(unique) == expected_count
        and 0 <= min(unique) <= max(unique) < 128,
        "top-four fixture geometry",
    )
    gold = camp / f"raw/c266-layer{layer}.stdout"
    expected = [
        f"CANONICAL_R2_TILE first={i} n={min(32, 153 - i)} bitwise=1 nonfinite=0 max_abs=0"
        for i in range(0, 153, 32)
    ] + [
        f"PASS_NATIVE_CANONICAL_R2_LAYER layer={layer} device={device} "
        f"logical_bytes_read={nbytes} O_DIRECT=1"
    ]
    check(
        common.sha(gold) == stdout_sha and gold.read_text().splitlines() == expected,
        "C266 tile results",
    )
    historical = common.read(camp / f"raw/c266-layer{layer}.json")
    check(
        len(historical["mapped_backend_libraries_sha256"]) == 5
        and historical["mapped_libraries_match_ldd"],
        "historical backend map",
    )
    return exe, capture, gold.read_bytes(), hashes


def cgroup(bounded):
    s = bounded.cgroup_state()
    check(
        s
        and s["memory_max"] == s["memory_high"] == CAP
        and s["swap_max"] == s["swap_current"] == 0,
        "cgroup cap/swap",
    )
    check(max(s["memory_peak"], s["memory_current"]) < CAP - 512 * 2**20, "preventive memory stop")
    check(
        not any(
            s[key][ev]
            for key in ["events", "events_local"]
            for ev in ("high", "max", "oom", "oom_kill")
        ),
        "cgroup event",
    )
    return {key: s[key] for key in ("memory_peak", "memory_current", "swap_current", "events")}


def run_family(repo, lab, model, out):
    out = out.resolve()
    out.mkdir()
    started = time.monotonic()
    sys.path[:0] = [str(repo / "research/qualification-retake/cuda35"), str(repo / "tools")]
    import c118_start_inventory as inv
    import layer as common
    import run_bounded as bounded
    from host_resource_policy import live_power
    from mappings import Guard
    from vma_identity import Reference

    receipt = {
        "schema": "tesy-c266-153rows-usb-v1",
        "status": "NOT_RUN",
        "arms": {str(layer): {"status": "NOT_RUN", "operator_calls": 0} for layer, *_ in ARMS},
        "protocol_sha256": common.sha(HERE / "protocolo.md"),
        "runner_sha256": common.sha(Path(__file__)),
    }
    current = None
    proc = None
    sample = None
    try:
        check(
            common.sha(Path(common.__file__))
            == "a5018675b9de9ca98e2be39f7f0a65d9126ed5978fcb580c004777b0658163a4",
            "CUDA35 shared helpers changed",
        )
        r3 = common.read(repo / "research/qualification-retake/cuda35/receipts/r3.json")
        check(
            r3["status"] == "PASS_SINGLE_CUDA35_ROUTED_REFERENCE"
            and common.sha(Path(sys.modules["vma_identity"].__file__)) == r3["vma_verifier_sha256"],
            "R3 VMA basis changed",
        )
        model = model.resolve(strict=True)
        target_stat = common.stat(model)
        prior = common.read(repo / "research/qualification-retake/host-evidence/receipt.json")
        check(
            target_stat[2] == prior["model_content"]["size_bytes"]
            and max(target_stat[3:]) / 1e9
            < dt.datetime.fromisoformat(prior["hash_started_utc"]).timestamp(),
            "model stat changed after full digest",
        )
        source, fs = common.shell(
            "findmnt", "--first-only", "-n", "-o", "SOURCE,FSTYPE", "-T", str(model)
        ).split()
        check(
            fs == "ext4"
            and common.shell(
                "lsblk",
                "-dn",
                "-o",
                "TRAN",
                "/dev/" + common.shell("lsblk", "-no", "PKNAME", source),
            )
            == "usb",
            "model transport",
        )
        receipt["target_sha256_previously_verified"] = prior["model_content"]["sha256"]
        check(
            receipt["target_sha256_previously_verified"] == r3["model_sha256_previously_verified"],
            "target identity",
        )
        receipt["host"] = {
            "gpu": common.shell(
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ),
            "driver_cuda": common.driver_cuda_header(common.shell("nvidia-smi")),
            "root_model_medium": "ext4 USB",
            "cpu": r3["host"]["cpu"],
            "cgroup_initial": cgroup(bounded),
        }
        check(
            "620.70.06" in receipt["host"]["gpu"] and receipt["host"]["driver_cuda"] == "13.5",
            "host driver identity",
        )
        camp = next(lab.glob("results/c266-new-shape-native-*"))
        pins = common.read(camp / "protocol.json")
        policy = common.read(camp / "resource-policy.json")
        check(
            common.sha(camp / "protocol.json")
            == "3f0b93f88b9e203e3fc1fc075afe61e977501aba433716dca87970f6bf15639a",
            "historic C266 protocol",
        )
        check(sum(s[3] for s in ARMS) <= 2 * 2**30, "logical byte budget")
        verified = [prepare(pins, camp, lab, *spec, common) for spec in ARMS]
        dso = r3["resolved_elf_sha256"]
        lib = lab / "backends/c269-layer-last-use/build-c269-cuda/bin"
        check(
            not any(k.startswith(("LD_", "OMP_", "GOMP_", "KMP_")) for k in os.environ),
            "ambient loader/OpenMP override",
        )
        env = os.environ | {"LD_LIBRARY_PATH": str(lib)}
        args = dict(
            policy=policy, cap_bytes=CAP, expected_power={"source": "AC", "profile": "performance"}
        )

        def sample(own=None):
            ids = common.shell(
                "nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"
            )
            check(not {int(i) for i in ids.splitlines()} - {own}, "concurrent CUDA process")
            s = {
                "gpu": bounded.gpu_state(prospective=True),
                "thermal": bounded.thermal_state(prospective=True),
                "power": live_power(),
                "mem_available_bytes": bounded.mem_available(),
            }
            inv.validate_sample(s, **args)
            return s

        with ExitStack() as stack:
            refs = {}
            for line in common.shell(
                "/lib64/ld-linux-x86-64.so.2",
                "--library-path",
                str(lib),
                "--list",
                str(verified[0][0]),
            ).splitlines():
                if " => " in line:
                    name, path = line.strip().split(" => ")
                    if name in dso:
                        refs[name] = Reference(stack, Path(path.split()[0]), dso[name])
            check(len(dso) == 9 and set(dso) == set(refs), "incomplete DSO selection")
            receipt["resolved_elf_sha256"] = dso
            receipt["map_classifier_sha256"] = common.sha(HERE / "mappings.py")
            for spec, data in zip(ARMS, verified, strict=True):
                layer, device, nexpert, nbytes, _ = spec
                exe, capture, gold, hashes = data
                root = out / str(layer)
                (root / "raw").mkdir(parents=True)
                current = receipt["arms"][str(layer)]
                current.update(device=device, source_sha256=hashes, distinct_experts=nexpert)
                for ref in refs.values():
                    ref.verify()
                run_id = f"c266-153rows-r2-{layer}"
                prep = inv.collect(root, run_id, sample=sample, duration_s=60, **args)
                inv.require_inventory(
                    root,
                    run_id,
                    prep,
                    duration_s=60,
                    max_age_s=3,
                    now=dt.datetime.now(dt.UTC),
                    **args,
                )
                current["preflight"] = {k: v for k, v in prep.items() if k != "path"}
                check(common.stat(model) == target_stat, "target changed at admission")
                cgroup(bounded)
                print(f"ADMITTED {device}{layer}", flush=True)
                t = time.monotonic()
                guard = Guard(refs)
                seen_lines = set()
                samples = []
                with (
                    (root / "raw/stdout").open("xb") as outlog,
                    (root / "raw/stderr").open("xb") as errlog,
                    (root / "raw/maps-observed.txt").open("x") as maplog,
                ):
                    proc = subprocess.Popen(
                        [exe, model, capture, str(layer), device],
                        env=env,
                        stdout=outlog,
                        stderr=errlog,
                    )
                    current["operator_calls"] = 1
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pending = pool.submit(sample, proc.pid)
                        while proc.poll() is None:
                            now = time.monotonic()
                            check(now - t < 60 and now - started < 480, "physical run budget")
                            cgroup(bounded)
                            try:
                                lines = Path(f"/proc/{proc.pid}/maps").read_text().splitlines()
                            except (FileNotFoundError, ProcessLookupError):
                                check(proc.poll() is not None, "lost process")
                                lines = []
                            for line in lines:
                                if line not in seen_lines:
                                    maplog.write(line + "\n")
                                    seen_lines.add(line)
                            maplog.flush()
                            check(maplog.tell() < 4 * 2**20, "raw VMA observation budget")
                            guard.scan(lines)
                            if pending.done():
                                samples.append(pending.result())
                                pending = pool.submit(sample, proc.pid)
                            time.sleep(0.01)
                        samples.append(pending.result())
                current.update(
                    exit=proc.returncode,
                    mapped_elf=sorted(guard.observed),
                    observed_map_sha256=common.sha(root / "raw/maps-observed.txt"),
                    live_samples=samples,
                )
                check(
                    proc.returncode == 0 and set(refs) == guard.observed,
                    "operator exit or incomplete mappings",
                )
                check((root / "raw/stdout").read_bytes() == gold, "numerical output differs")
                check(common.stat(model) == target_stat, "target changed after operator")
                for ref in refs.values():
                    ref.verify()
                current.update(
                    status="PASS_NUMERICAL_ROWS153",
                    logical_bytes=nbytes,
                    stdout_sha256=common.sha(root / "raw/stdout"),
                    postflight=sample(),
                    cgroup_end=cgroup(bounded),
                )
                print(f"PASS {device}{layer}", flush=True)
                proc = None
                current = None
        check(time.monotonic() - started < 480, "family wall budget")
        check(
            sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) < 16 * 2**20 - 65536,
            "result size budget",
        )
        receipt["status"] = "PASS_CPU0_CUDA25_ROWS153"
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        receipt["failure"] = f"{type(exc).__name__}: {exc}"
        receipt["status"] = (
            "FAIL" if any(a["operator_calls"] for a in receipt["arms"].values()) else "NOT_RUN"
        )
        if current is not None:
            current["status"] = "FAIL" if current["operator_calls"] else "NOT_RUN"
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        if current is not None and sample is not None:
            try:
                current["postflight"] = sample()
                current["cgroup_end"] = cgroup(bounded)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                current["postflight_failure"] = str(exc)
        receipt["family_wall_s"] = time.monotonic() - started
        tmp = out / "receipt.json.part"
        tmp.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
        tmp.rename(out / "receipt.json")
    print(receipt["status"], receipt.get("failure", ""), flush=True)
    return int(receipt["status"] != "PASS_CPU0_CUDA25_ROWS153")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "lab", "model", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    a = ap.parse_args()
    raise SystemExit(run_family(a.repo, a.lab, a.model, a.new_output_dir))
