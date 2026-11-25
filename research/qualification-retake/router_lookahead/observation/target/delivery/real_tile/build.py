"""Build the isolated two-layer CPU client from immutable manager, GGML and BLAS inputs."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
QUAL = HERE.parents[4]
ROOT = QUAL.parents[1]
R = run_path(str(PARENT / "run.py"))
F = run_path(str(QUAL / "packed_real_layer/build.py"))
need, sha, git = (R[k] for k in ("need", "sha", "git"))
BLAS = "432e1c1739731468ba305771af96773939e43016643e2d630f58cb45b6670e96"
CRYPTO = "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72"
PARENT_OVERLAY = hashlib.sha256(
    git(ROOT, "show", "c263a677:" + str((PARENT / "overlay.py").relative_to(ROOT)))
).hexdigest()


def build(a, out, r):
    need(not git(ROOT, "status", "--porcelain"), "measurement checkout is dirty")
    r.update(
        commit=git(ROOT, "rev-parse", "HEAD").decode().strip(),
        tree=git(ROOT, "rev-parse", "HEAD^{tree}").decode().strip(),
    )
    libs = {name: (a.libs / name).resolve(strict=True) for name in F["LIBS"]}
    crypto = Path("/lib64/libcrypto.so.3").resolve(strict=True)
    blas = a.blas.resolve(strict=True)
    need(sha(crypto) == CRYPTO and sha(blas) == BLAS, "crypto or BLAS changed")
    need(all(sha(lib) == F["LIBS"][name] for name, lib in libs.items()), "GGML libraries changed")
    need(sha(Path("/usr/bin/c++")) == R["COMPILER"], "compiler changed")
    src = out / "source"
    r["manager_inputs"] = R["P"]["canonical"](R["extract"](a.backend, src))
    parent_patch = PARENT / "overlay.py"
    need(sha(parent_patch) == PARENT_OVERLAY, "packed delivery overlay changed")
    patch = run_path(str(parent_patch))
    patch["apply"](src / "src")
    # The frozen marker overlay made exactly one substitution in the store header.
    # Restoring it restores the entire original production header byte-for-byte.
    store = src / "src/c291-expert-store.h"
    store.write_text(patch["change"](store.read_text(), "slab=4096", "slab=4406400"))
    need(
        store.read_bytes() == git(a.backend, "show", R["PIN"] + ":src/c291-expert-store.h"),
        "C291 production record geometry",
    )
    manager = src / "src/llama-moe-stream.cpp"
    s = patch["change"](
        manager.read_text(),
        "void llama_moe_stream::worker_loop() {",
        "extern void tile_register_worker();\nextern void tile_claim(int,int,int,uint64_t);\n"
        "void llama_moe_stream::worker_loop() {\n    tile_register_worker();",
    )
    s = patch["change"](
        s,
        "        sl.slot_claimed[w.slot] = 1;",
        "        sl.slot_claimed[w.slot] = 1;\n        tile_claim(sl.il,w.expert,w.slot,w.gen);",
    )
    s = patch["change"](
        s,
        "    for (auto & w : workers) {\n        w.join();\n    }",
        "    for (auto & w : workers) {\n        w.join();\n    }\n"
        "    extern void tile_workers_joined(llama_moe_stream &);\n"
        "    tile_workers_joined(*this);",
    )
    manager.write_text(s)
    helper = out / "pairs-finish.inc"
    helper.write_text(F["functions"](ROOT / "tools/block_expert_reuse_operator.cpp"))
    operator = PARENT.parent / "operator/operator.cpp"
    r["operator_sha256"] = sha(operator)
    r["source_sha256"] = {
        p.name: sha(p)
        for p in [
            HERE / "build.py",
            HERE / "native.cpp",
            HERE / "graph.inc",
            HERE / "protocol.md",
            parent_patch,
            helper,
            manager,
            store,
            src / "src/c305-cpu-stage.h",
        ]
    }
    binary = out / "real-tile"
    command = [
        "/usr/bin/c++",
        "-std=gnu++17",
        "-O2",
        "-g0",
        "-pthread",
        "-fPIC",
        "-pie",
        "-DTESY_C47_CPU_SKIP_PARKED",
        "-DTESY_STORE_TESTING",
        "-DTESY_C305_STAGE_TESTING",
        "-ffunction-sections",
        "-fdata-sections",
        "-I" + str(out),
        *["-I" + str(src / d) for d in ("src", "include", "ggml/include")],
        HERE / "native.cpp",
        operator,
        *[src / "src" / n for n in R["P"]["BUILD_INPUTS"]],
        "-Wl,--gc-sections",
        "-Wl,--wrap=pread",
        "-Wl,--wrap=ggml_backend_tensor_set",
        *libs.values(),
        blas,
        crypto,
        "-Wl,-rpath," + str(blas.parent),
        "-ldl",
        "-o",
        binary,
    ]
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "OPENBLAS_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": str(a.libs) + ":" + str(blas.parent),
    }
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(
            command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180
        )
    seen = subprocess.check_output(["/usr/bin/ldd", binary], text=True, env=env)
    (out / "loader.log").write_text(seen)
    need(
        "not found" not in seen and not any(x in seen for x in ("libcuda", "libllama", "nvidia")),
        "CUDA/provider contamination",
    )
    providers = {}
    for line in seen.splitlines():
        if " => /" in line:
            name, path = line.strip().split(" => ")
            resolved = Path(path.split()[0]).resolve(strict=True)
            providers[name] = [str(resolved), sha(resolved)]
    for path in [*libs.values(), blas, crypto]:
        need([str(path), sha(path)] in providers.values(), "wrong loader resolution")
    r.update(
        binary=binary.name,
        binary_sha256=sha(binary),
        providers=providers,
        compiler_sha256=R["COMPILER"],
        status="PASS_REAL_TILE_BUILD",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "libs", "blas", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    r = {"status": "FAIL_PRESERVED"}
    try:
        build(a, a.new_output_dir, r)
    except Exception as exc:
        r["error"] = str(exc)
        raise
    finally:
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps(r, sort_keys=True, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
