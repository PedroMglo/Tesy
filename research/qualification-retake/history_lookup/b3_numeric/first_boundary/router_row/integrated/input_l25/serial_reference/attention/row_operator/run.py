"""Freeze the native operator ELF and operands, then compare one bounded CUDA process."""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(str(HERE / "operands.py"))
P, S, need, read, sha, save = (D[k] for k in ("P", "S", "need", "read", "sha", "save"))
MIB = 1 << 20
TAG = ("A", "B", "S", "B-alt", "S-alt", "mutant")
FILES = {
    "ggml/src/ggml-cuda/fattn.cu": (
        "003afde0510c67a31c4d0b5fd7490416487f2246aaf2bbb80567e655dba95df6"
    ),
    "ggml/src/ggml-cuda/fattn-common.cuh": (
        "47537d7980d81f7dc9daa18698f5fdbb990ef6b916fa75fed4bc0bbfd1aa08cb"
    ),
    "src/llama-graph.cpp": "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288",
    "src/llama-kv-cache.cpp": D["KV"]["SOURCES"]["src/llama-kv-cache.cpp"],
    "src/models/openai-moe.cpp": D["KV"]["SOURCES"]["src/models/openai-moe.cpp"],
}


def shell(argv, **options):
    return subprocess.check_output(argv, text=True, timeout=30, **options).strip()


def provenance(a):
    git = P["prepare"].git
    need(
        git(HERE, "rev-parse", "HEAD") == a.commit
        and not git(HERE, "status", "--porcelain")
        and git(a.backend, "rev-parse", "HEAD") == "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
        and not git(a.backend, "status", "--porcelain")
        and all(sha(a.backend / k) == v for k, v in FILES.items())
        and sha(HERE / "protocol.md") == D["METHOD"],
        "clean source and method",
    )
    return dict(
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=D["METHOD"],
        family_sha256=D["FAMILY"],
        sources={k: sha(HERE / k) for k in ("fixture.cpp", "run.py", "operands.py")},
    )


def build(a, out):
    data, refs, cfg = D["reconstruct"](a.family, a.model, a.inventory)
    inputs = out / "inputs"
    inputs.mkdir()
    for name, body in (data | {k + ".gold": v for k, v in refs.items()}).items():
        (inputs / name).write_bytes(body)
    compiler = Path("/usr/bin/g++-15")
    need(sha(a.full_build / "receipt.json") == P["BUILD"], "observer build authority")
    origin = read(a.full_build / "receipt.json")
    need(sha(compiler) == origin["compiler_sha256"], "compiler")
    libs = a.backend / "build-c269-cuda/bin"
    env = S["SC"]["OLD"]["environment"]([str(libs)])
    cmd = [
        str(compiler),
        "-std=c++17",
        "-O2",
        "-MMD",
        "-MF",
        str(out / "headers.d"),
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
    closure = shell(["/usr/bin/ldd", "-r", str(out / "fixture")], env=env)
    need("not found" not in closure and "undefined symbol" not in closure, "loader unresolved")
    (out / "ldd.txt").write_text(closure + "\n")
    providers = {
        k: dict(file=str(path.resolve(strict=True)), sha256=sha(path))
        for k, path in S["SC"]["OLD"]["interpret"](closure).items()
    }
    need(
        {"libggml-cuda.so.0", "libggml-base.so.0"} <= providers.keys()
        and all(origin["current_providers"][k] == v for k, v in providers.items()),
        "fixture startup provider",
    )
    initialized = read(a.family / "receipt.json")["arms"]["AR"]["loader"]["initialized"]
    headers = (out / "headers.d").read_text().replace("\\\n", " ").split(":", 1)[1].split()
    dep = {str(Path(p).resolve()): sha(Path(p)) for p in headers}
    return dict(
        status="BUILT_ATTENTION_OPERANDS",
        current_providers=providers,
        permitted_providers=initialized,
        compiler_sha256=sha(compiler),
        headers_sha256=dep,
        elf_sha256=sha(out / "fixture"),
        files={x.name: sha(x) for x in inputs.iterdir()},
        model_sha256=cfg["pinned"]["model_sha256"],
        input_model_payload_B=256,
        policy_sha256=sha(a.family / "AR/resource-policy.json"),
        model_forwards=0,
    )


def sampled(policy, pid, baseline):
    inventory = run_path(str(S["QUAL"].parents[1] / "tools/c118_start_inventory.py"))
    s = inventory["server"]
    gpu = s.gpu_state(prospective=True)
    obs = dict(
        thermal=s.thermal_state(prospective=True),
        gpu=gpu,
        power=inventory["live_power"](),
        mem_available_bytes=s.mem_available(),
    )
    inventory["validate_sample"](
        obs,
        policy=policy,
        cap_bytes=2 << 30,
        expected_power=dict(source="AC", profile="performance"),
    )
    processes = shell(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"])
    ids = {int(x) for x in processes.splitlines() if x}
    need(
        ids <= ({pid} if pid else set())
        and (not pid or ids == {pid})
        and (baseline is None or gpu["used_mib"] - baseline <= 1024),
        "competing CUDA process or footprint",
    )
    return obs


def loaded(pid, build, cache):
    observed = {}
    authority = P["N"]["AU"]
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or not fields[-1].startswith("/") or ".so" not in Path(fields[-1]).name:
            continue
        path = Path(fields[-1])
        inode = path.stat()
        if str(path) not in cache:
            key = authority["reference_key"](str(path), authority["identity"](path))
            cache[str(path)] = D["stat_id"](inode), sha(path), key
        stamp, digest, key = cache[str(path)]
        need(key == authority["mapping_key"](fields), "live VMA of " + path.name)
        need(
            stamp == D["stat_id"](inode) and build["permitted_providers"].get(path.name) == digest,
            "foreign or replaced provider " + path.name,
        )
        observed[path.name] = digest
    need(
        all(Path(v["file"]).name in observed for v in build["current_providers"].values()),
        "missing initial mapping",
    )
    return observed


def execute(a, out, r, cg):
    need(sha(a.build / "receipt.json") == a.build_sha256, "sealed build")
    b = read(a.build / "receipt.json")
    need(
        b["status"] == "BUILT_ATTENTION_OPERANDS"
        and all(
            b[k] == r[k] for k in ("commit", "tree", "sources", "protocol_sha256", "family_sha256")
        )
        and b["elf_sha256"] == sha(a.build / "fixture")
        and all(sha(Path(k)) == v for k, v in b["headers_sha256"].items())
        and {p.name: sha(p) for p in (a.build / "inputs").iterdir()} == b["files"]
        and sha(a.family / "receipt.json") == D["FAMILY"]
        and sha(a.family / "AR/resource-policy.json") == b["policy_sha256"],
        "sealed input or ELF",
    )
    policy = read(a.family / "AR/resource-policy.json")
    device = shell(
        ["nvidia-smi", "--query-gpu=name,driver_version,compute_cap", "--format=csv,noheader"]
    )
    need(device == "NVIDIA GeForce RTX 4060 Laptop GPU, 620.73.04, 8.9", "GPU and driver")
    r.update(
        device=device,
        admission=sampled(policy, None, None),
        build_sha256=a.build_sha256,
        model_forwards=0,
    )
    inputs = a.build / "inputs"
    outputs = out / "device"
    env = S["SC"]["OLD"]["environment"]([str(a.backend / "build-c269-cuda/bin")])
    deadline = time.monotonic() + 60
    runtime, mem, cache = {}, {}, {}
    with (
        (out / "stdout").open("xb") as log,
        (out / "stderr").open("xb") as err,
        subprocess.Popen(
            [a.build / "fixture", inputs, outputs], env=env, stdout=log, stderr=err
        ) as proc,
    ):
        r["operator_starts"] = 1
        try:
            for key in ("before", "after"):
                flag = outputs / (key + ".ready")
                while not flag.exists():
                    need(
                        proc.poll() is None and time.monotonic() < deadline,
                        "missing checkpoint " + key,
                    )
                    time.sleep(0.01)
                need(flag.read_text() == key, "stage marker")
                mem[key] = sampled(policy, proc.pid, r["admission"]["gpu"]["used_mib"])
                runtime[key] = loaded(proc.pid, b, cache)
                (outputs / (key + ".ack")).touch(exist_ok=False)
            need(proc.wait(timeout=max(0.1, deadline - time.monotonic())) == 0, "CUDA exit")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    r.update(
        live=mem,
        loaded=runtime,
        after_exit=sampled(policy, None, r["admission"]["gpu"]["used_mib"]),
    )
    rows = [line.split() for line in (out / "stdout").read_text().splitlines()]
    need(
        len(rows) == 16
        and all(
            len(v) == 3 and v[0] == "device_memory" and 0 < int(v[1]) <= int(v[2]) for v in rows
        ),
        "eight graph memory observations",
    )
    result = D["grade"](
        {tag: (outputs / (tag + ".f32")).read_bytes() for tag in TAG},
        {k: (inputs / (k + ".gold")).read_bytes() for k in ("AR", "B3")},
    )
    save(out / "grade.json", result)
    return dict(
        status=result["decision"],
        grade_sha256=sha(out / "grade.json"),
        device_free_min_B=min(int(v[1]) for v in rows),
        cgroup_peak_B=int((cg / "memory.peak").read_text()),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("build", "run"))
    for name in (
        "family",
        "backend",
        "new-output-dir",
        "full-build",
        "model",
        "inventory",
        "build",
    ):
        p.add_argument(
            "--" + name, type=Path, required=name in ("family", "backend", "new-output-dir")
        )
    p.add_argument("--commit", required=True)
    p.add_argument("--build-sha256")
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    t = time.monotonic()
    r = dict(status="FAIL_PRESERVED", operator_starts=0, model_forwards=0)
    try:
        cg = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::", 1)[
            1
        ].lstrip("/")
        need(
            int((cg / "memory.max").read_text()) == 2 << 30
            and int((cg / "memory.swap.max").read_text()) == 0,
            "2 GiB/zero swap scope",
        )
        r.update(provenance(a))
        r.update(build(a, out) if a.mode == "build" else execute(a, out, r, cg))
        need(
            int((cg / "memory.swap.current").read_text()) == 0
            and time.monotonic() - t < 180
            and sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) < 16 * MIB,
            "resource budget",
        )
    except Exception as e:
        r.update(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    r["wall_s"] = time.monotonic() - t
    r["raw_sha256"] = {
        str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
