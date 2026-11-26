"""Supervise four C291/C269 tile transitions in a fresh external 2 GiB GPU fixture scope."""

import argparse
import hashlib
import inspect
import json
import os
import re
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
INTEGRATED = HERE.parents[2]
QUAL = INTEGRATED.parents[1]
ARMS = ("reference", "disk", "bank", "broken")
GPU_RUN = "81aeaeea4b590d02d4c3303a9ede74961452e0696df5d206d0c3cfc1870d6b70"
CPU = "18eedc6035445c59b1e27845df5412dea2260b70c30f27224a8025635e1577d5"
GEN = "3b9c94261e71e3a0aef16311670ca907343e89b5474af3bbf13899e5eadc6c5d"


def need(condition, why):
    if not condition:
        raise ValueError(why)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def prior_case():
    """Specialize the frozen C118/handshake loop without changing the published R03."""
    path = INTEGRATED / "t1_manager_cuda/device/run.py"
    need(sha(path) == GPU_RUN, "R03 acquisition source")
    old = run_path(path)
    text = inspect.getsource(old["case"])
    edits = [
        ("monitor_sample, paths):", "monitor_sample, paths, pack, gold, progress):"),
        (
            '[build / "device", arm, out / arm]',
            '[build / "device", arm, pack, gold, out / arm / "raw.json"]',
        ),
        (
            "            os.close(wfd)",
            "            progress.update(child_launches=1, pid=child.pid)\n"
            "            os.close(wfd)",
        ),
        ("time.monotonic() - start < 30", "time.monotonic() - start < 60"),
        ("30 - (time.monotonic() - start)", "60 - (time.monotonic() - start)"),
        (
            '                sample("after_exit")',
            '                need(not sample("after_exit"), "GPU not released")',
        ),
        ("journal=parse(outlog, arm, paths)", 'stderr_sha256=sha(raw / (arm + ".stderr"))'),
    ]
    for before, after in edits:
        need(text.count(before) == 1, "R03 acquisition seam: " + before)
        text = text.replace(before, after)
    namespace = dict(old["case"].__globals__)
    exec(compile(text, "<C291 tile scoped acquisition>", "exec"), namespace)
    return old, namespace["case"]


def generated_pack(nvme, out, cpu):
    need(
        not nvme.exists()
        and nvme.parent.is_dir()
        and not nvme.is_relative_to(out)
        and not out.is_relative_to(nvme),
        "new NVMe directory",
    )
    mount = json.loads(
        subprocess.check_output(
            ["findmnt", "--json", "--target", nvme.parent, "--output", "FSTYPE,SOURCE"]
        )
    )["filesystems"]
    need(
        len(mount) == 1
        and mount[0]["fstype"] == "btrfs"
        and re.fullmatch(r"/dev/nvme\d+n\d+(?:p\d+)?(?:\[.*\])?", mount[0]["source"]),
        "internal Btrfs NVMe",
    )
    gen = QUAL / "packed_worker/generate.py"
    need(sha(gen) == GEN, "pack generator")
    run_path(gen)["generate"](nvme)
    pack, goldfile = nvme / "experts.pack", nvme / "gold.json"
    gold = json.loads(goldfile.read_bytes())
    need(
        goldfile.is_file()
        and sha(goldfile) == cpu["gold_sha256"]
        and pack.stat().st_size == gold["pack_bytes"] == 79552512,
        "independent pack gold",
    )
    with (out / "gold.json").open("xb") as f:
        f.write(goldfile.read_bytes())
    return pack, goldfile, gold


def execute(a, out, r):
    old, case = prior_case()
    b = run_path(HERE / "build.py")
    dev = run_path(HERE / "review.py")
    cpu_review = run_path(HERE.parent / "review.py")
    tree = old["builder"]["freeze"](a.commit)
    cold = run_path(INTEGRATED / "cold_read_fixture/runner.py")
    load, io = cold["load"], cold["io"]
    io.CAP, io.STOPS = 2**31, 1856 * 2**20
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "scope identity")
    ram = load(a.ram_receipt, old["RAM_AUTHORITY"])
    profile = run_path(QUAL / "packed_layer_service/profile.py")
    provider, unchanged = profile["monitor_provider"](SimpleNamespace(token=io.stat_id))
    need(
        provider == ram["monitor_provider"]
        and Path("/sys/module/nvidia/version").read_text().strip() == "620.70.06",
        "GPU driver",
    )
    c55 = load(a.c55, a.c55_sha256)
    policy = load(a.c55.with_name("resource-policy.json"), c55["canonical_policy_sha256"])
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "C55 admission",
    )
    cpu = load(a.cpu_receipt, CPU)
    need(cpu["status"] == "PASS_C291_TILE_TRANSITION_CPU_FAMILY", "CPU qualification")
    build = a.build_dir.resolve(strict=True)
    receipt = load(build / "receipt.json", a.build_sha256)
    need(
        receipt["status"] == "PASS_TILE_CUDA_BUILD_ONLY"
        and receipt["commit"] == a.commit
        and receipt["tree"] == tree
        and receipt["protocol_sha256"] == b["PROTOCOL"]
        and receipt["source_sha256"] == hashlib.sha256(b["source"]()).hexdigest()
        and receipt["map_sha256"] == sha(a.map),
        "build identity",
    )
    paths, files = b["providers"](a.map)

    def authenticated():
        need(
            sha(build / "device") == receipt["binary_sha256"]
            and sha(build / "allowed.tsv") == receipt["allow_sha256"]
            and {p.name: p.resolve(strict=True) for p in (build / "libs").iterdir()} == paths,
            "binary/provider closure",
        )
        b["verify_files"](paths, files)
        unchanged()

    authenticated()
    r.update(
        commit=a.commit,
        tree=tree,
        build_sha256=a.build_sha256,
        c55_sha256=a.c55_sha256,
        cpu_receipt_sha256=CPU,
        protocol_sha256=b["PROTOCOL"],
        acquisition_sha256=GPU_RUN,
        generator_sha256=GEN,
        provider=provider,
        unit=a.unit,
        scope_cap=io.CAP,
        model_forwards=0,
        arms={},
    )
    (out / "raw").mkdir()
    pack, goldfile, gold = generated_pack(a.new_nvme_dir.resolve(), out, cpu)
    identity = run_path(QUAL / "packed_worker/run.py")["identity"]
    original = identity(pack)
    r.update(
        pack_sha256=gold["pack_sha256"],
        gold_sha256=cpu["gold_sha256"],
        pack_bytes=gold["pack_bytes"],
    )
    active = run_path(INTEGRATED / "t1_native_sink/measure.py")["active_sample"]
    rows = {}
    for arm in ARMS:
        age = (
            datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])
        ).total_seconds()
        need(0 <= age < 3300 - 125, "C55 through C118 and child")
        row = r["arms"][arm] = {"child_launches": 0}
        target = out / arm
        target.mkdir()
        stat = case(out, arm, a.unit, build, io, policy, cold, active, paths, pack, goldfile, row)
        row.update(stat)
        raw = target / "raw.json"
        data = json.loads(raw.read_bytes())
        row["raw_sha256"] = sha(raw)
        need(
            data["status"] == "PASS_C291_TILE_TRANSITION_CUDA" and data["arm"] == arm,
            "native result",
        )
        for role, soname in (("ggml", "libggml-base.so.0"), ("crypto", "libcrypto.so.3")):
            p = paths[soname]
            witness = data["providers"][role]
            need(
                Path(witness["path"]) == p and witness["identity"] == identity(p),
                "provider " + role,
            )
        align = data["offset_alignment"]
        need(
            type(align) is int
            and align > 0
            and gold["pack_stride"] % align == 0
            and data["read_extent"] == ((3 * gold["slab"] + align - 1) // align) * align
            and data["pack_sha256"] == gold["pack_sha256"]
            and data["pack_proof_bytes"] == 2 * original["size_bytes"]
            and identity(pack) == original
            and sha(goldfile) == cpu["gold_sha256"],
            "transport/FD",
        )
        rows[arm] = dict(data, status="PASS_C291_TILE_TRANSITION_CPU")
        row["manager"] = cpu_review["case"](arm, rows[arm], gold)
        row["device"] = dev["check_child"](arm, target, out / "reference", data, gold)
        row["files"] = {
            p.name: {"bytes": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(target.iterdir())
            if p.is_file()
        }
        unchanged()
    r["verified"] = cpu_review["family"](rows, gold)
    authenticated()
    r["peak_bytes"] = io.scope()
    need(
        set(p.name for p in pack.parent.iterdir()) == {"gold.json", "experts.pack"}
        and identity(pack) == original
        and sha(goldfile) == cpu["gold_sha256"],
        "cleanup ownership",
    )
    pack.unlink()
    goldfile.unlink()
    pack.parent.rmdir()
    r.update(status="PASS_C291_TILE_TRANSITION_CUDA_FAMILY", pack_cleaned=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("commit", "unit", "build-sha256", "c55-sha256"):
        p.add_argument("--" + name, required=True)
    for name in (
        "build-dir",
        "c55",
        "ram-receipt",
        "map",
        "cpu-receipt",
        "new-nvme-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    r = {}

    def timeout(*_):
        raise TimeoutError("family deadline")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(600)
    try:
        execute(a, out, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    r["family_wall_s"] = time.monotonic() - start
    with (out / "receipt.json").open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
