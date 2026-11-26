"""Compile a private CPU0 policy fixture from the sealed C291 manager and C266 harness."""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
spec = importlib.util.spec_from_file_location("packed_tile_build", HERE.parent / "build.py")
tile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tile)
need, sha = tile.need, tile.sha
CRYPTO = "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72"
PARENT = {
    "layer.cpp": "e1240b2981b49163efa9156ac9bc15f7865770f7c1016e26a8ea61ad9d97c14a",
    "slot_witness.h": "31f6fa07cb1606efcbdee913a6982b8478bbdab405b352be2d79d779303cec90",
    "build.py": "a781699f893a8b323c0879578e4f61f27c64423dfeaba6559c43b81e466f0e2a",
}
SOURCES = ("build.py", "policy.patch", "policy_state.h", "policy_observe.h")


def victim_guard(original, modified):
    """Prove the original victim function body survives in full after the opt-in mask."""
    sig = "int32_t llama_moe_stream::pick_victim_locked("
    end = "void llama_moe_stream::reserve_slot_locked("

    def body(text):
        start = text.index(sig)
        return text[start : text.index(end, start)]

    old = body(original)
    new = body(modified)
    suffix = old[old.index("    int32_t v = -1;") :]
    need(new.endswith(suffix), "stock victim search, ties or keep handling changed")
    gate = new[: -len(suffix)]
    need(
        gate.count("if (policy_use_backing) {") == 1
        and gate.count("if (!empty && backed) keep=filtered.data();") == 1
        and gate.count("keep=") == 1
        and gate.rstrip().endswith("}"),
        "preference must only restrict eligible choices under opt-in",
    )


def build(args, result):
    root = args.new_output_dir.resolve()
    repo, libs = args.repo.resolve(), args.libs.resolve()
    worker = tile.trusted_worker(repo)
    need(repo == HERE.parents[3], "run the builder inside the selected measurement revision")
    need(not worker.git(repo, "status", "--porcelain").strip(), "clean revision required")
    need(all(sha(HERE.parent / n) == h for n, h in PARENT.items()), "changed parent harness")
    crypto = Path("/usr/lib64/libcrypto.so.3").resolve()
    need(sha(crypto) == CRYPTO, "OpenSSL library identity")
    need(all(sha(libs / n) == h for n, h in tile.LIBS.items()), "C269 math runtime identity")
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(libs)}

    def run(argv, label):
        with (root / (label + ".log")).open("xb") as output:
            subprocess.run(
                argv,
                cwd=root,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=180,
                check=True,
            )

    src = root / "private"
    worker.extract(args.backend.resolve(), src)
    used = src / "src/llama-moe-stream.cpp"
    original = used.read_text()
    result.update(
        commit=worker.git(repo, "rev-parse", "HEAD").decode().strip(),
        tree=worker.git(repo, "rev-parse", "HEAD^{tree}").decode().strip(),
        worker_commit=worker.PIN,
        worker_tree=worker.TREE,
        native_sources={name: sha(HERE / name) for name in SOURCES},
        parent_sources=PARENT,
        crypto_sha256=CRYPTO,
        libs=tile.LIBS,
        compiler_sha256=sha(Path("/usr/bin/g++").resolve()),
    )
    for name in ("layer.cpp", "slot_witness.h"):
        shutil.copyfile(HERE.parent / name, src / name)
    for name in ("policy_state.h", "policy_observe.h"):
        shutil.copyfile(HERE / name, src / name)
    run(
        [
            "/usr/bin/patch",
            "--batch",
            "--fuzz=0",
            "--forward",
            "-p1",
            "-d",
            src,
            "-i",
            HERE / "policy.patch",
        ],
        "patch",
    )
    victim_guard(original, used.read_text())
    helper = src / "pairs-finish.inc"
    helper.write_text(tile.functions(repo / "tools/block_expert_reuse_operator.cpp"))
    result["extracted_helpers_sha256"] = sha(helper)
    result["patched_sha256"] = {
        name: sha(src / name)
        for name in ("layer.cpp", "slot_witness.h", "src/llama-moe-stream.cpp")
    }
    binary = root / "policy-layer"
    argv = [
        "/usr/bin/g++",
        "-std=c++17",
        "-O0",
        "-g0",
        "-Wall",
        "-Wextra",
        "-pthread",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-ffunction-sections",
        "-fdata-sections",
        "-DTESY_C47_CPU_SKIP_PARKED",
        "-DTESY_STORE_TESTING",
        *["-I" + str(src / d) for d in ("src", "include", "ggml/include")],
        src / "layer.cpp",
        *[src / "src" / name for name in worker.BUILD_INPUTS],
        "-Wl,--gc-sections",
        "-Wl,--wrap=pread",
        "-Wl,--wrap=ggml_backend_tensor_set",
        *[libs / name for name in tile.LIBS],
        crypto,
        "-ldl",
        "-o",
        binary,
    ]
    run(argv, "compile")
    run(["/usr/bin/ldd", binary], "providers")
    linked = (root / "providers.log").read_text()
    need(
        all(word not in linked for word in ["not found", "libcuda", "libggml-cuda", "libllama"]),
        "unexpected numeric provider",
    )
    for soname, path in {
        **{name.rsplit(".", 2)[0]: libs / name for name in tile.LIBS},
        "libcrypto.so.3": crypto,
    }.items():
        hits = [line for line in linked.splitlines() if line.strip().startswith(soname + " => ")]
        need(len(hits) == 1 and Path(hits[0].split()[2]).samefile(path), "wrong " + soname)
    run([binary, "--self-test"], "counterexamples")
    need(
        (root / "counterexamples.log").read_text().strip() == "PASS_C291_TILE_COUNTEREXAMPLES",
        "original graph counterexamples",
    )
    result.update(status="PASS_C291_CPU0_POLICY_BUILD", executables={"policy-layer": sha(binary)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "backend", "libs", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(exist_ok=False)
    result = {"status": "FAIL_PRESERVED"}
    try:
        build(args, result)
    except Exception as exc:
        result["error"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    (args.new_output_dir / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
