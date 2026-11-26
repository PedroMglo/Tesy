"""Prepare and run the L25 routed operator on its two full-graph reference cuts."""

import argparse
import struct
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(str(HERE / "operands.py"))
H = run_path(str(D["ATT"] / "run.py"))
R, need, sha, read, save = (D[k] for k in ("R", "need", "sha", "read", "save"))
KNOWN_BUILD = "cebf96f41ae3423a24679d445bc1e07e73b344ce66ef61bdac075465adb286ea"
CUDA_SOURCE = "0de01a8cb0502a7eea43b130504dcfeebb6fbf9dce31c57f884337419b7071d5"


def provenance(a):
    git = H["P"]["prepare"].git
    need(
        git(HERE, "rev-parse", "HEAD") == a.commit
        and not git(HERE, "status", "--porcelain")
        and git(a.backend, "rev-parse", "HEAD") == "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
        and not git(a.backend, "status", "--porcelain")
        and sha(a.backend / "ggml/src/ggml-cuda/ggml-cuda.cu") == CUDA_SOURCE
        and sha(a.backend / "src/llama-graph.cpp") == H["FILES"]["src/llama-graph.cpp"]
        and sha(HERE / "protocol.md") == D["METHOD"],
        "clean source, dispatch and protocol",
    )
    return dict(
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=D["METHOD"],
        serial_sha256=D["SERIAL"],
        block_sha256=D["BLOCK"],
        sources={f: sha(HERE / f) for f in ("fixture.cpp", "run.py", "operands.py")},
    )


def compile_fixture(a, out, origin):
    old = H["S"]["SC"]["OLD"]
    libs = a.backend / "build-c269-cuda/bin"
    env = old["environment"]([libs])
    compiler = Path("/usr/bin/g++-15")
    need(sha(compiler) == origin["compiler_sha256"], "compiler identity")
    headers = out / "headers.d"
    cmd = [
        str(compiler),
        "-std=c++17",
        "-O2",
        "-MMD",
        "-MF",
        str(headers),
        "-I",
        str(a.backend / "ggml/include"),
        str(HERE / "fixture.cpp"),
        "-L",
        str(libs),
        "-Wl,-rpath," + str(libs),
        "-lggml-cuda",
        "-lggml-base",
        "-o",
        str(out / "fixture"),
    ]
    save(out / "compiler.json", cmd)
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    closure = H["shell"](["/usr/bin/ldd", "-r", str(out / "fixture")], env=env)
    need("not found" not in closure and "undefined symbol" not in closure, "native closure")
    (out / "ldd.txt").write_text(closure + "\n")
    providers = {
        k: dict(file=str(v.resolve(strict=True)), sha256=sha(v))
        for k, v in old["interpret"](closure).items()
    }
    need(origin["current_providers"] == providers, "identical numerical providers")
    deps = headers.read_text().replace(chr(92) + "\n", " ").split(":", 1)[1].split()
    return dict(
        current_providers=providers,
        permitted_providers=origin["permitted_providers"],
        compiler_sha256=sha(compiler),
        elf_sha256=sha(out / "fixture"),
        headers_sha256={str(Path(k).resolve()): sha(Path(k)) for k in deps},
    )


def build(a, out):
    origin = R["reopen"](a.known_build, KNOWN_BUILD)
    data, refs = D["references"](a.serial, a.block)
    cfg = read(a.block / "ON/full-resource.json")
    need(
        cfg["model_stat"] == read(a.serial / "AR/attention-resource.json")["model_stat"]
        and cfg["pinned"]["model_sha256"] == origin["model_sha256"]
        and sha(a.serial / "AR/resource-policy.json") == origin["policy_sha256"],
        "model and policy",
    )
    inputs = out / "inputs"
    inputs.mkdir(mode=0o700)
    for k, v in (data | {k + ".gold": v for k, v in refs.items()}).items():
        (inputs / k).write_bytes(v)
    ids = struct.unpack("<12i", data["logical.i32"])
    ranges = D["components"](a.model, a.inventory, cfg, ids, inputs)
    need(
        len(ranges) == 60 and sum(v["bytes"] for v in ranges.values()) == 132537600, "expert union"
    )
    save(out / "ranges.json", ranges)
    binary = compile_fixture(a, out, origin)
    return dict(
        status="BUILT_ROUTED_FFN",
        **binary,
        model_sha256=origin["model_sha256"],
        policy_sha256=origin["policy_sha256"],
        known_build_sha256=KNOWN_BUILD,
        input_model_payload_B=sum(v["bytes"] for v in ranges.values()),
        routed_ids=ids,
        ranges_sha256=sha(out / "ranges.json"),
        model_stat=cfg["model_stat"],
    )


def run(a, out, r, cg):
    b = R["reopen"](a.build, a.build_sha256)
    need(
        b["status"] == "BUILT_ROUTED_FFN"
        and all(b[k] == r[k] for k in provenance(a))
        and all(sha(Path(k)) == v for k, v in b["headers_sha256"].items())
        and sha(a.build / "fixture") == b["elf_sha256"]
        and sha(a.serial / "AR/resource-policy.json") == b["policy_sha256"],
        "sealed build and policy",
    )
    policy = read(a.serial / "AR/resource-policy.json")
    device = H["shell"](
        ["nvidia-smi", "--query-gpu=name,driver_version,compute_cap", "--format=csv,noheader"]
    )
    need(device == "NVIDIA GeForce RTX 4060 Laptop GPU, 620.73.04, 8.9", "target GPU/driver")
    r.update(admission=H["sampled"](policy, None, None), device=device, build_sha256=a.build_sha256)
    env = H["S"]["SC"]["OLD"]["environment"]([a.backend / "build-c269-cuda/bin"])
    inputs, device_dir = a.build / "inputs", out / "device"
    deadline = time.monotonic() + 60
    baseline = r["admission"]["gpu"]["used_mib"]
    cache, mem, maps = {}, {}, {}
    with (
        (out / "stdout").open("xb") as log,
        (out / "stderr").open("xb") as err,
        subprocess.Popen(
            [a.build / "fixture", inputs, device_dir], env=env, stdout=log, stderr=err
        ) as proc,
    ):
        r["operator_starts"] = 1
        try:
            for key in ("before", "after"):
                flag = device_dir / (key + ".ready")
                while not flag.exists():
                    need(proc.poll() is None and time.monotonic() < deadline, "checkpoint " + key)
                    time.sleep(0.01)
                need(flag.read_text() == key, "native marker")
                mem[key] = H["sampled"](policy, proc.pid, baseline)
                maps[key] = H["loaded"](proc.pid, b, cache)
                (device_dir / (key + ".ack")).touch(exist_ok=False)
            need(proc.wait(timeout=max(0.1, deadline - time.monotonic())) == 0, "CUDA exit")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    r.update(live=mem, loaded=maps, after_exit=H["sampled"](policy, None, baseline))
    rows = [line.split() for line in (out / "stdout").read_text().splitlines()]
    need(
        len(rows) == 22
        and all(
            len(v) == 3 and v[0] == "device_memory" and 0 < int(v[1]) <= int(v[2]) for v in rows
        ),
        "eleven graphs",
    )
    g = D["grade"](
        {k: (device_dir / (k + ".f32")).read_bytes() for k in D["TAGS"]},
        {k: (inputs / (k + ".gold")).read_bytes() for k in ("AR", "B3")},
        b["routed_ids"],
    )
    save(out / "grade.json", g)
    return dict(
        status=g["decision"],
        grade_sha256=sha(out / "grade.json"),
        device_free_min_B=min(int(v[1]) for v in rows),
        cgroup_peak_B=int((cg / "memory.peak").read_text()),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("build", "run"))
    for k in (
        "serial",
        "block",
        "backend",
        "new-output-dir",
        "known-build",
        "model",
        "inventory",
        "build",
    ):
        p.add_argument("--" + k, type=Path, required=k in ("serial", "backend", "new-output-dir"))
    p.add_argument("--build-sha256")
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    needed = (
        ("block", "known_build", "model", "inventory")
        if a.mode == "build"
        else ("build", "build_sha256")
    )
    if any(not getattr(a, k) for k in needed):
        p.error("missing inputs for " + a.mode)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    r = dict(status="FAIL_PRESERVED", operator_starts=0, model_forwards=0)
    try:
        cg = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::", 1)[
            1
        ].lstrip("/")
        need(
            int((cg / "memory.max").read_text()) == 2 << 30
            and int((cg / "memory.swap.max").read_text()) == 0,
            "cgroup resources",
        )
        r.update(provenance(a))
        r.update(build(a, out) if a.mode == "build" else run(a, out, r, cg))
        need(
            int((cg / "memory.swap.current").read_text()) == 0
            and time.monotonic() - start < 180
            and sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
            < (150 if a.mode == "build" else 16) << 20,
            "budget",
        )
    except Exception as e:
        r.update(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    r["wall_s"] = time.monotonic() - start
    r["raw_sha256"] = {
        str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
