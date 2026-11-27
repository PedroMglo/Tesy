"""Run the bounded model-free physical CPU slot-representation gate."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BUILD = run_path(HERE.parent / "build.py")
ROOT, mm = BUILD["ROOT"], BUILD["mm"]
PAIR = ROOT / "research/qualification-retake/nvme_admission/io_pair"
sys.path.insert(0, str(PAIR))
G = run_path(PAIR / "run.py")
need, sha = mm.need, mm.sha
CAP = 2 << 30
METHOD = "3bc765826e0d4331287e8a5cb4f1ba066916867af2636fac88ccd1fce7302023"
C55 = "2ab72091749637911fd3aa2a79a2800957110caa259ce9f2caab59102eaf7dad"


def run(a, out, rec):
    group = BUILD["cgroup"](CAP)
    libs = a.backend / "build-c269-cuda/bin"
    need(
        mm.git(ROOT, "rev-parse", "HEAD") == a.commit
        and not mm.git(ROOT, "status", "--porcelain")
        and mm.git(a.backend, "rev-parse", "HEAD") == mm.PIN
        and not mm.git(a.backend, "status", "--porcelain")
        and sha(HERE / "slot-layout.md") == METHOD
        and sha(HERE / "composition.json")
        == "02beb453cbc65d6d481a45c5f7faae51cc39f27dcfc64a5539735c1a6ea0bdc8",
        "source or admission",
    )
    c55file = a.window / "receipt.json"
    c55 = json.loads(c55file.read_bytes())
    pf = a.window / "resource-policy.json"
    policy = json.loads(pf.read_bytes())
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(
        sha(c55file) == C55
        and c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and 0 <= age < 3600
        and sha(pf) == c55["canonical_policy_sha256"]
        and G["operational_session_ready"](policy)[0]
        and not G["concurrent"](),
        "physical window or competing workload",
    )
    disk = G["disk"](out, "nvme")
    sources = {k: sha(HERE / k) for k in ("slot_layout.cpp", "slot_layout.py")}
    reader_file = a.reader / "src/c291-direct-reader.h"
    reader_sha = sha(reader_file)
    need(
        mm.git(a.reader, "rev-parse", "HEAD") == "c89c88b342054223e3f27a17fbfd0954803147ac"
        and not mm.git(a.reader, "status", "--porcelain")
        and reader_sha == "cb386577d0b424d531a484d81619e29887b2419dd03c05578004b0878f601af6",
        "C291 reader source",
    )
    rec.update(reader_sha256=reader_sha, retake_protocol_sha256=sha(HERE / "slot-retake.md"))
    pins = {name: sha(libs / name) for name in (mm.BASE, mm.CPU)}
    cc = "/usr/bin/g++-15"
    need(
        pins == {mm.BASE: mm.BASE_SHA, mm.CPU: mm.CPU_SHA}
        and sha(cc) == "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a",
        "toolchain",
    )
    rec.update(
        commit=a.commit,
        tree=mm.git(ROOT, "rev-parse", "HEAD^{tree}"),
        backend=mm.PIN,
        protocol_sha256=METHOD,
        sources=sources,
        libraries=pins,
        compiler_sha256=sha(cc),
        resource_window_sha256=C55,
        c55_age_s=age,
        filesystem=G["mount"](out),
        disk=disk.parent.name,
        caps=dict(memory=CAP, swap=0, seconds=180, output_bytes=128 << 20),
        host=os.uname().nodename,
        kernel=os.uname().release,
        model_forwards=0,
        gpu_forwards=0,
        arms={},
    )
    (out / "provenance.json").write_text(json.dumps(rec, sort_keys=True, indent=2) + "\n")
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "TMPDIR": str(out),
        "LD_LIBRARY_PATH": str(libs),
        "OMP_NUM_THREADS": "8",
        "OMP_DYNAMIC": "FALSE",
    }
    start = time.monotonic()
    maxima = {}

    def sample():
        obs = G["live_sample"]()
        G["validate_sample"](
            obs,
            policy=policy,
            cap_bytes=CAP,
            expected_power={"source": "AC", "profile": "performance"},
        )
        need(G["host_pressure"]() < 10 and time.monotonic() - start < 180, "host pressure or wall")
        with (out / "telemetry.jsonl").open("a") as f:
            f.write(json.dumps(obs, allow_nan=False) + "\n")
        values = dict(
            cpu_c=obs["thermal"]["cpu_tctl_c"],
            gpu_c=obs["gpu"]["temperature_c"],
            nvme_c=max(obs["thermal"]["nvme_composite_by_sensor"].values()),
        )
        for k, v in values.items():
            maxima[k] = max(maxima.get(k, v), v)

    def invoke(argv, label):
        rec["stage"] = label
        with (out / (label + ".log")).open("xb") as log:
            proc = subprocess.Popen(
                list(map(str, argv)), env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT
            )
            try:
                while proc.poll() is None:
                    sample()
                    try:
                        proc.wait(0.3)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        need(proc.returncode == 0, "native failure in " + label)

    exe, source = out / "fixture", out / "records.bin"
    invoke(
        [
            cc,
            "-std=c++20",
            "-O2",
            "-pthread",
            "-I" + str(a.backend / "ggml/include"),
            "-I" + str(reader_file.parent),
            HERE / "slot_layout.cpp",
            libs / mm.CPU,
            libs / mm.BASE,
            "-o",
            exe,
        ],
        "compile",
    )
    rec["loaded_providers"] = mm.loader(
        exe, env, {"libggml-cpu.so.0": libs / mm.CPU, "libggml-base.so.0": libs / mm.BASE}
    )
    rec["elf_sha256"] = sha(exe)
    invoke([exe, "make", source], "generate")
    source.chmod(0o400)
    need(source.stat().st_size == 5 * 13221888, "five records")
    rec["input_sha256"] = sha(source)
    for role in ("A", "B", "C", "MUTANT"):
        path = out / (role + ".f32")
        invoke([exe, role, source, path], role)
        words = (out / (role + ".log")).read_text().strip().splitlines()[-1].split()
        slab, stride, mem, offset, reads, sets = map(int, words[1:])
        need(
            words[0] == role
            and (slab, stride, reads) == (4406400, 13221888, 5)
            and 4096 % mem == 4096 % offset == 0
            and sets == (15 if role in ("A", "B") else 0),
            "native delivery accounting",
        )
        data = path.read_bytes()
        half = len(data) // 2
        need(
            half == 2880 * 4 * 53 * 3 * 4 and len(data) == 2 * half and data[:half] != data[half:],
            "row population or stale slot",
        )
        digest = hashlib.sha256(data).hexdigest()
        if role != "A":
            need(
                (digest == rec["arms"]["A"]["sha256"]) == (role != "MUTANT"),
                "independent words or insensitive mutant",
            )
        rec["arms"][role] = dict(
            sha256=digest,
            bytes=len(data),
            generation_sha256=[hashlib.sha256(v).hexdigest() for v in (data[:half], data[half:])],
            direct_reads=reads,
            requested_bytes=reads * stride,
            weight_sets=sets,
            weight_set_payload_bytes=sets * slab,
            memory_alignment=mem,
            offset_alignment=offset,
        )
    sample()
    need(
        sha(source) == rec["input_sha256"]
        and sum(f.stat().st_size for f in out.iterdir()) < 128 << 20,
        "immutable input or budget",
    )
    rec.update(
        status="GO_CPU_RECORD_SLOT_FIXTURE_ONLY",
        maxima=maxima,
        memory_peak_bytes=int((group / "memory.peak").read_text()),
        swap_peak_bytes=int((group / "memory.swap.peak").read_text()),
        elapsed_s=time.monotonic() - start,
        telemetry_sha256=sha(out / "telemetry.jsonl"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("window", "backend", "reader", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    rec = {"status": "FAIL_PRESERVED"}
    try:
        run(a, a.new_output_dir, rec)
    except Exception as exc:
        rec.update(error=str(exc))
    path = a.new_output_dir / ".receipt.tmp"
    with path.open("x") as f:
        json.dump(rec, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    path.rename(a.new_output_dir / "receipt.json")
    print(rec["status"], rec.get("error", ""))
    raise SystemExit(rec["status"] == "FAIL_PRESERVED")
