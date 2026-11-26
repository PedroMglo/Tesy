"""Inspect the same C291 FFN descriptors before and inside the C269 CPU dispatch."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUALIFY = Path("research/qualification-retake")
C55 = "c02b90596719ecb32dce050c73cf56b6d9c8273a0c4742a46b75ba9f4cd10659"
SUFFIX = "37f7ceec65cab37640dbf4b5b1f48bec19165d097a84adbfb956a01ea7db1f13"
C269 = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
CAP = 4 << 30
STOP = 7 << 29
EXPECTED = "e569253a2f984a84"
BASE_ENV = {
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "CUDA_VISIBLE_DEVICES": "",
    "OMP_NUM_THREADS": "8",
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def checked(p, digest):
    need(sha(p) == digest, "digest mismatch: " + p.name)
    return json.loads(p.read_bytes())


def git(path, *args):
    cmd = [
        "/usr/bin/git",
        "--no-optional-locks",
        "-c",
        "index.threads=1",
        "-c",
        "core.preloadIndex=false",
        "-C",
        path,
        *args,
    ]
    return subprocess.check_output(cmd, text=True, timeout=15).strip()


def cgroup():
    c = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("0::")[
        -1
    ].lstrip("/")
    need(
        int((c / "memory.max").read_text()) == CAP
        and int((c / "memory.high").read_text()) == STOP
        and int((c / "memory.swap.max").read_text()) == 0,
        "E4 scope/high/swap",
    )
    return c


def validate_events(c):
    events = {
        k: int(v)
        for k, v in (line.split() for line in (c / "memory.events").read_text().splitlines())
    }
    need(
        all(events[k] == 0 for k in ("high", "max", "oom", "oom_kill"))
        and int((c / "memory.peak").read_text()) < STOP
        and int((c / "memory.swap.current").read_text()) == 0,
        "scope memory stop",
    )
    return events


def run(argv, env, prefix, scope, r):
    r["commands"][prefix.name] = list(map(str, argv))
    start = time.monotonic()
    with (
        prefix.with_suffix(".stdout").open("xb") as out,
        prefix.with_suffix(".stderr").open("xb") as err,
    ):
        child = subprocess.Popen(argv, stdout=out, stderr=err, env=env, start_new_session=True)
        try:
            while child.poll() is None:
                validate_events(scope)
                need(time.monotonic() - start < 120, "phase deadline")
                time.sleep(0.05)
            need(child.returncode == 0, "phase failed: " + prefix.name)
            validate_events(scope)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


def phase_result(label, native, seam, elf, preload, providers):
    post = label == "post"
    phase = "cpu_graph_compute" if post else "before_scheduler"
    need(
        native["status"] == "PASS_C269_TOPOLOGY_FRONTEND"
        and native["phase"] == phase
        and native["seam_path"] == str(preload)
        and native["backend_splits"] == int(post)
        and native["weight_payload_input_bytes"] == native["wave_calls"] == native["workers"] == 0
        and native["graph_nodes"] == 110
        and native["graph_mmid_nodes"] == 24
        and native["graph_fingerprint"] == EXPECTED,
        "native topology or work",
    )
    need(
        seam["status"] == "PASS_SEAM_CAPTURE"
        and seam["phase"] == phase
        and seam["kernel_executed"] is False
        and seam["structure"] in {"CERTIFIED_ALL", "CUT_REJECTED", "UNIDENTIFIED_GRAPH"},
        "invalid CPU observation",
    )
    cpu, base = providers
    need(
        Path(seam["caller"]).samefile(cpu if post else elf)
        and Path(seam["cpu_provider"]).samefile(cpu)
        and Path(seam["base_provider"]).samefile(base),
        "wrong caller/provider",
    )
    if seam["structure"] != "UNIDENTIFIED_GRAPH":
        need(
            seam["graph_fingerprint"] == EXPECTED
            and len(seam["nodes"]) == seam["graph_nodes"] == 110
            and seam["graph_mmid_nodes"] == 24
            and len(seam["rows"]) == 8,
            "claimed graph identity",
        )
        certified = sum(row["certified"] is True for row in seam["rows"])
        need(
            seam["certified_waves"] == certified
            and (seam["structure"] == "CERTIFIED_ALL") == (certified == 8),
            "certified population",
        )
    return {
        k: seam[k]
        for k in (
            "phase",
            "graph_nodes",
            "graph_mmid_nodes",
            "graph_fingerprint",
            "certified_waves",
            "structure",
        )
    }


def inspect(a, r):
    out = a.new_output_dir
    repo, src, backend = a.repo.resolve(), a.suffix_build.resolve(), a.backend.resolve()
    scope = cgroup()
    c55 = checked(a.c55_receipt, C55)
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and c55["canonical_memory"]["cap_max_bytes"] >= CAP
        and not c55["concurrent"],
        "C55 capacity",
    )
    need(
        HERE == repo / QUALIFY / "parked_fusion" and not git(repo, "status", "--porcelain"),
        "clean study",
    )
    need(
        git(backend, "rev-parse", "HEAD") == C269
        and not git(backend, "status", "--porcelain", "--", "ggml", "vendor/nlohmann"),
        "C269 headers",
    )
    r.update(
        commit=git(repo, "rev-parse", "HEAD"),
        tree=git(repo, "rev-parse", "HEAD^{tree}"),
        c269_commit=C269,
        c55_sha256=C55,
        suffix_build_receipt_sha256=SUFFIX,
    )
    ref = checked(src / "receipt.json", SUFFIX)
    source = src / "src"
    for n, v in ref["worker_input_manifest"].items():
        need(sha(source / n) == v["sha256"], "C291 source " + n)
    r["source_sha256"] = {
        n: sha(HERE / n) for n in ("topology.py", "topology.patch", "seam.cpp", "protocol.md")
    }
    ref_header = repo / QUALIFY / "cpu0_suffix/suffix-clock.h"
    need(
        sha(ref_header) == ref["sources"]["suffix-clock.h"]
        and sha(src / "layer.cpp") == ref["layer_patched_sha256"]
        and sha(src / "pairs-finish.inc") == ref["helper_sha256"],
        "original graph constructor",
    )
    libs = backend / "build-c269-cuda/bin"
    providers = [libs / n for n in ("libggml-cpu.so.0.15.3", "libggml-base.so.0.15.3")]
    need(all(sha(p) == ref["libs"][p.name] for p in providers), "original libraries")
    gcc = "/usr/bin/g++"
    need(sha(Path(gcc)) == ref["compiler_sha256"], "original compiler")
    r.update(
        compiler_sha256=ref["compiler_sha256"],
        providers=ref["libs"],
        original_graph_source_sha256=ref["layer_patched_sha256"],
        original_pairs_finish_sha256=ref["helper_sha256"],
    )
    env = BASE_ENV | {"LD_LIBRARY_PATH": str(libs)}
    layer = out / "frontend.cpp"
    layer.write_bytes((src / "layer.cpp").read_bytes())
    run(
        ["/usr/bin/patch", "--batch", "--forward", "--fuzz=0", layer, HERE / "topology.patch"],
        env,
        out / "patch",
        scope,
        r,
    )
    generated = layer.read_text()
    need(
        all(
            s not in generated
            for s in (
                "pack.bin",
                "routing(",
                "prepare.json",
                "ggml_backend_tensor_set(",
                "read<float>",
                "ggml_backend_graph_compute(",
                "clock_gettime",
                "graph_start_ns",
            )
        ),
        "payload/compute code in descriptor frontend",
    )
    r["generated_tu_sha256"] = sha(layer)
    elf, preload = out / "frontend", out / "seam.so"
    common = [gcc, "-std=c++17", "-O0", "-g0", "-pthread", "-fPIC", "-fno-plt"]
    run(
        [
            *common,
            "-shared",
            "-I" + str(backend / "ggml/src"),
            "-I" + str(backend / "ggml/include"),
            "-I" + str(backend / "vendor"),
            "-MMD",
            "-MF",
            out / "seam.d",
            HERE / "seam.cpp",
            *providers,
            "-ldl",
            "-o",
            preload,
        ],
        env,
        out / "seam-compile",
        scope,
        r,
    )
    run(
        [
            *common,
            "-pie",
            "-ffunction-sections",
            "-fdata-sections",
            "-DTESY_C47_CPU_SKIP_PARKED",
            "-DTESY_STORE_TESTING",
            "-I" + str(src),
            "-I" + str(ref_header.parent),
            *["-I" + str(source / p) for p in ("src", "include", "ggml/include")],
            layer,
            *[
                source / "src" / s
                for s in ("llama-moe-stream.cpp", "llama-impl.cpp", "llama-mmap.cpp")
            ],
            "-Wl,--gc-sections",
            *providers,
            "-ldl",
            "-o",
            elf,
        ],
        env,
        out / "frontend-compile",
        scope,
        r,
    )
    # GCC emits these project paths without spaces in the native dependency file.
    dependencies = (out / "seam.d").read_text().replace("\\\n", " ").split(": ", 1)[1].split()
    r["seam_dependencies"] = {str(Path(p).resolve()): sha(Path(p)) for p in dependencies}
    r.update(frontend_sha256=sha(elf), seam_elf_sha256=sha(preload))
    linkenv = env | {"LD_PRELOAD": str(preload), "LD_BIND_NOW": "1"}
    run(["/lib64/ld-linux-x86-64.so.2", "--list", elf], linkenv, out / "resolution", scope, r)
    resolved = (out / "resolution.stdout").read_text()
    need(
        not any(s in resolved for s in ("not found", "libcuda", "libnvidia", "libggml-cuda")),
        "unexpected backend",
    )
    for mode in ("pre", "post"):
        target = out / (mode + "-seam.json")
        run(
            [elf, mode, preload],
            linkenv | {"TESY_FUSION_SEAM_JSON": str(target)},
            out / mode,
            scope,
            r,
        )
        native = json.loads((out / (mode + ".stdout")).read_text())
        (out / (mode + "-native.json")).write_text(json.dumps(native, sort_keys=True) + "\n")
        seam = json.loads(target.read_text())
        r["phases"][mode] = phase_result(mode, native, seam, elf, preload, providers) | {
            "native": native,
            "seam_sha256": sha(target),
            "seam_bytes": target.stat().st_size,
        }
    r["memory_peak_bytes"] = int((scope / "memory.peak").read_text())
    r["scope_memory_events"] = validate_events(scope)
    r["scope_io_stat"] = (scope / "io.stat").read_text().splitlines()
    pre, post = [r["phases"][phase]["structure"] for phase in ("pre", "post")]
    if "UNIDENTIFIED_GRAPH" in (pre, post):
        r["decision"] = "INCONCLUSIVE"
    elif post == "CUT_REJECTED":
        r["decision"] = "NO_GO_LOCAL_FUSION"
    else:
        r["decision"] = "GO_FIXTURE"
    r["status"] = "PASS_C269_TOPOLOGY_AUDIT"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("repo", "suffix-build", "backend", "c55-receipt", "new-output-dir"):
        p.add_argument("--" + n, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir = a.new_output_dir.resolve()
    a.new_output_dir.mkdir(mode=0o700)
    start = time.monotonic()
    r = {
        "status": "FAIL_PRESERVED",
        "decision": "INCONCLUSIVE",
        "commands": {},
        "phases": {},
        "cap_bytes": CAP,
        "stop_bytes": STOP,
        "weight_input_bytes": 0,
        "model_forwards": 0,
    }
    try:
        inspect(a, r)
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        r["failure"] = str(exc)
    r["elapsed_s"] = time.monotonic() - start
    r["child_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    dest = a.new_output_dir / "receipt.json"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    tmp.rename(dest)
    print(r["status"], r["decision"], sha(dest))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
