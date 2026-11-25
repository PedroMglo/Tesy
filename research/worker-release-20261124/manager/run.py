"""Build the pinned C305 blocking manager and verify native OFF/ON on synthetic inputs."""

import argparse
import hashlib
import json
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "c94780b12820c7b3fb20f2a9acf38bb27506c6ae"
TREE = "e418713c063a33214d5bf75f3ff25b40090ab7a1"
BASE_DSO = "6ed6609cc6862c3d971cef8bacde6f0c0dd6275a4bb3a263a28bac5063826195"
SLAB = 4_406_400
REGION = (128 * SLAB + 4095) // 4096 * 4096
MIB = 2**20
ARTIFACTS = 200 * MIB


def require(truth, message):
    if not truth:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def tree_bytes(root):
    return sum(
        p.stat().st_blocks * 512 for p in root.rglob("*") if p.is_file() and not p.is_symlink()
    )


def limits():
    # An address-space limit also bounds RSS on Linux (Linux ignores RLIMIT_RSS).
    cap = 1280 * MIB
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    resource.setrlimit(resource.RLIMIT_FSIZE, (ARTIFACTS, ARTIFACTS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_bounded(argv, root, name, env, cwd=None):
    start = time.monotonic()
    with (root / f"{name}.out").open("xb") as log, (root / f"{name}.err").open("xb") as err:
        command = ["/usr/bin/time", "-o", str(root / f"{name}.rss"), "-f", "%M", *argv]
        with subprocess.Popen(
            command,
            cwd=cwd or root,
            env=env,
            stdout=log,
            stderr=err,
            start_new_session=True,
            preexec_fn=limits,
        ) as proc:
            try:
                status = proc.wait(timeout=120)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                os.killpg(proc.pid, signal.SIGKILL)
                raise
    require(status == 0, f"{name} stopped with exit {status}; see private logs")
    size = tree_bytes(root)
    require(size <= ARTIFACTS, "allocated file budget exceeded")
    return {
        "elapsed_s": round(time.monotonic() - start, 6),
        "max_rss_kib": int((root / f"{name}.rss").read_text()),
        "allocated_bytes": size,
    }


def generate(path):
    digest = hashlib.sha256()
    with path.open("xb") as handle:
        handle.truncate(3 * REGION + 4096)
        for k in range(3):
            for e in (1, 2, 3, 4, 8, 9, 10, 11):
                cycle = bytes((29 * e + 61 * k + 11 * j) % 256 for j in range(251))
                payload = (cycle * ((SLAB + 250) // 251))[:SLAB]
                handle.seek(k * REGION + e * SLAB)
                handle.write(payload)
                digest.update(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o444)
    st = path.stat()
    require(
        st.st_size == 3 * REGION + 4096 < 2048 * MIB and st.st_blocks * 512 < 160 * MIB,
        "file geometry or sparse allocation",
    )
    return {
        "logical_bytes": st.st_size,
        "allocated_bytes": st.st_blocks * 512,
        "written_slabs_sha256_component_then_expert": digest.hexdigest(),
    }


def checkout_sources(backend, private):
    def git(*args):
        return subprocess.check_output(
            ["git", "--no-replace-objects", "-C", backend, *args], timeout=20
        )

    require(git("rev-parse", PIN + "^{tree}").decode().strip() == TREE, "backend tree")
    src = [
        "llama-moe-stream.cpp",
        "llama-moe-stream.h",
        "llama-mmap.cpp",
        "llama-mmap.h",
        "llama-impl.cpp",
        "llama-impl.h",
        "c294-service-window.h",
        "c305-cpu-stage.h",
        "c291-direct-reader.h",
        "c291-expert-store.h",
        "c269-last-use-order.h",
    ]
    headers = (
        git("ls-tree", "-r", "--name-only", PIN, "ggml/include", "include", "vendor/nlohmann")
        .decode()
        .splitlines()
    )
    for rel in [*headers, *("src/" + f for f in src)]:
        dest = private / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(git("show", PIN + ":" + rel))


def measure(backend, dso, out):
    from verify_result import verify

    out.mkdir()
    unit_files = [
        "run.py",
        "verify_result.py",
        "fixture.cpp",
        "fixture_observer.h",
        "observer.patch",
        "protocolo.md",
    ]
    receipt = {
        "schema": "tesy-c305-native-blocking-manager-v1",
        "decision": "FAIL",
        "source_commit": PIN,
        "source_tree": TREE,
        "files": {n: sha(HERE / n) for n in unit_files},
        "phases": {},
        "arms": [],
    }
    try:
        git = ["git", "--no-replace-objects", "-C", str(HERE)]
        head, tree = subprocess.check_output(
            [*git, "rev-parse", "HEAD", "HEAD^{tree}"], timeout=10, text=True
        ).splitlines()
        dirty = subprocess.check_output(
            [*git, "status", "--porcelain=v1", "--untracked-files=normal"], timeout=10
        )
        receipt["tesy"] = {"commit": head, "tree": tree, "clean": not dirty}
        require(not dirty, "confirmation requires a clean Tesy worktree")
        require(sha(dso) == BASE_DSO, "CPU ggml-base DSO identity")
        receipt["libggml_base_sha256"] = BASE_DSO
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(out),
            "LC_ALL": "C",
            "MALLOC_ARENA_MAX": "2",
            "OMP_NUM_THREADS": "1",
            "LD_LIBRARY_PATH": str(dso.parent),
        }
        private = out / "backend"
        checkout_sources(backend, private)
        receipt["base_manager_sha256"] = sha(private / "src/llama-moe-stream.cpp")
        phases = receipt["phases"]
        phases["hooks"] = run_bounded(
            ["patch", "--batch", "--forward", "-p1", "-i", HERE / "observer.patch"],
            out,
            "hooks",
            env,
            cwd=private,
        )
        phases["compiler"] = run_bounded(["g++", "--version"], out, "compiler", env)
        receipt["compiler"] = (out / "compiler.out").read_text().splitlines()[0]
        receipt["compiler_sha256"] = sha(Path(shutil.which("g++", path=env["PATH"])))
        argv = [
            "g++",
            "-std=c++17",
            "-pthread",
            "-O0",
            "-g0",
            "-Wall",
            "-Wextra",
            "-ffunction-sections",
            "-fdata-sections",
            "-I" + str(HERE),
        ]
        argv += ["-I" + str(private / p) for p in ("src", "include", "ggml/include")]
        exe = out / "manager-fixture"
        src = private / "src"
        phases["build"] = run_bounded(
            [
                *argv,
                HERE / "fixture.cpp",
                src / "llama-moe-stream.cpp",
                src / "llama-impl.cpp",
                src / "llama-mmap.cpp",
                "-Wl,--gc-sections",
                "-Wl,--wrap=pread",
                dso,
                "-lz",
                "-o",
                exe,
            ],
            out,
            "build",
            env,
        )
        phases["linkage"] = run_bounded(["ldd", exe], out, "linkage", env)
        libraries = (out / "linkage.out").read_text()
        require(
            "libggml-base.so.0" in libraries
            and "not found" not in libraries
            and not any(s in libraries.lower() for s in ("cuda", "nvidia", "libllama")),
            "native dependencies",
        )
        matching = [line for line in libraries.splitlines() if "libggml-base.so" in line]
        require(
            len(matching) == 1
            and sha(Path(matching[0].split("=>")[1].strip().split()[0])) == BASE_DSO,
            "resolved CPU DSO hash",
        )
        receipt["executable_sha256"] = sha(exe)
        receipt["input"] = generate(out / "synthetic.bin")
        agreement = None
        for n, mode in enumerate(("OFF", "ON", "ON", "OFF"), 1):
            ident = f"arm-{n}-{mode.lower()}"
            arm = out / ident
            arm.mkdir()
            usage = run_bounded([exe, mode, out / "synthetic.bin", arm], out, ident, env)
            raw = json.loads((arm / "raw.json").read_bytes())
            result = verify(raw, mode == "ON", arm)
            key = result["destinations_sha256"], raw["counters"], raw["terminal"]
            require(agreement is None or key == agreement, "OFF/ON content or work differs")
            agreement = key
            receipt["arms"].append(
                {
                    "arm": n,
                    "mode": mode,
                    "result": result,
                    "raw_sha256": sha(arm / "raw.json"),
                    "usage": usage,
                }
            )
        receipt["decision"] = "PASS_NATIVE_BLOCKING_MANAGER_FIXTURE"
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        receipt["allocated_bytes_before_receipt"] = tree_bytes(out)
        with tempfile.NamedTemporaryFile("w", dir=out, delete=False) as tmp:
            json.dump(receipt, tmp, indent=2, allow_nan=False)
            tmp.write("\n")
        os.replace(tmp.name, out / "receipt.json")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--ggml-base", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        measure(args.backend.resolve(), args.ggml_base.resolve(), args.new_output_dir.resolve())[
            "decision"
        ]
    )
