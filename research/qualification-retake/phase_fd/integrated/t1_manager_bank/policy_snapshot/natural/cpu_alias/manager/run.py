"""Build and run the five CPU-only C291 worker cases in an exclusive scope."""

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = next(p for p in HERE.parents if (p / "AGENTS.md").is_file())
OLD = PROJECT / "research/qualification-retake/packed_worker/run.py"
CASES = ("alias", "no-bank", "early", "short", "stale")


def load(path):
    spec = importlib.util.spec_from_file_location(path.parent.name + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(row, mode):
    check(
        row["mode"] == mode
        and row["status"] == "PASS_EXPECTED_MANAGER_OBSERVATION"
        and row["manager_destructor_returned"],
        "native post-join verdict",
    )
    publications = row["publications_slot_expert_gen"]
    if mode in ("stale", "short"):
        check(
            publications == [[0, 0, 1]]
            and row["sticky_load_failed"]
            and row["installed_generation"] == 1
            and row["failed_ticket_state"]
            == [1, 3 if mode == "stale" else 2, 1, int(mode == "stale")]
            and row["source_bytes"] == 2 * 13221888 - (4096 if mode == "short" else 0),
            "failed work published or stale generation lost",
        )
    else:
        count = 6 if mode == "no-bank" else 5
        check(
            publications[0] == [0, 0, 1]
            and publications[-1] == [0, 0, 3]
            and sorted(publications[1:-1]) == [[0, 1, 2], [1, 2, 1], [2, 3, 1], [3, 4, 1]]
            and row["concurrent_workers"] == 4
            and row["reads"] == count
            and row["source_bytes"] == count * 13221888
            and row["bank_hits"] == 6 - count
            and row["stale_release_rejected"]
            and row["three_other_slots_published_with_two_old_readers"]
            and row["independent_old_reader_checks"] == [mode != "early"] * 2
            and row["last_reader_blocked_replacement"] == (mode != "early")
            and row["restored_original_backing"] == (mode != "no-bank")
            and row["replacement_unique_backing_bytes"]
            == (4 if mode == "no-bank" else 5) * 13221888
            and row["restored_unique_backing_bytes"] == 4 * 13221888,
            "unmatched work, generation, last reader or materialized bytes",
        )
        if mode != "early":
            check(publications[-2] == [0, 1, 2], "guard failed to delay the blocked worker")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    args = ap.parse_args()
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    r = {"status": "FAIL_PRESERVED", "commands": {}, "arms": {}}
    try:
        check(
            sha(OLD) == "67523bc7c44d6cf1182b45008e7414d160254b62a64c1ffe142fe934ab65509e",
            "shared scope and C291 extractor pin",
        )
        old = load(OLD)
        observe = old.cgroup_reader(PROJECT, args.unit)
        r["scope_initial"] = observe()
        commit = old.git(PROJECT, "rev-parse", "HEAD").decode().strip()
        check(
            commit == args.head and not old.git(PROJECT, "status", "--porcelain"),
            "clean study commit",
        )
        r.update(
            commit=commit,
            tree=old.git(PROJECT, "rev-parse", "HEAD^{tree}").decode().strip(),
            c291=old.PIN,
            c291_tree=old.TREE,
            kernel=platform.release(),
            started=old.utc(),
        )
        r["source_sha256"] = {
            p.name: sha(p)
            for p in (
                HERE / n for n in ("protocol.md", "run.py", "lease.h", "fixture.cpp", "overlay.py")
            )
        }
        source = out / "src"
        r["inputs"] = old.extract(args.backend, source)
        load(HERE / "overlay.py").materialize(source)
        r["worker_sha256"] = sha(source / "src/llama-moe-stream.cpp")
        lib = (
            args.backend.parent / "c269-layer-last-use/build-c269-cuda/bin/libggml-base.so.0.15.3"
        ).resolve(strict=True)
        check(sha(lib) == old.LIBS["ggml"], "C269 base identity")
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "LD_LIBRARY_PATH": str(lib.parent),
            "OMP_NUM_THREADS": "1",
            "CUDA_VISIBLE_DEVICES": "",
        }

        def run(argv, label):
            return old.record_command(argv, out, label, env, r["commands"], start + 600, observe)

        exe = out / "worker-alias"
        compiler = Path("/usr/bin/g++")
        r["compiler_sha256"] = sha(compiler)
        command = [
            compiler,
            "-std=c++17",
            "-DTESY_STORE_TESTING",
            "-pthread",
            "-O1",
            "-g0",
            "-fPIC",
            "-pie",
            "-ffunction-sections",
            "-fdata-sections",
            "-I" + str(HERE),
        ]
        command += ["-I" + str(source / n) for n in ("src", "include", "ggml/include")]
        command += [
            HERE / "fixture.cpp",
            *(source / "src" / n for n in old.BUILD_INPUTS),
            "-Wl,--gc-sections",
            lib,
            "-o",
            exe,
        ]
        run(command, "build")
        libraries = (run(["/usr/bin/ldd", exe], "loader") / "stdout").read_text()
        check(
            lib.parent.joinpath("libggml-base.so.0").resolve() == lib
            and f"libggml-base.so.0 => {lib.parent}/libggml-base.so.0 " in libraries
            and "libggml-cuda" not in libraries
            and "libcuda.so" not in libraries,
            "CPU-only runtime providers",
        )
        r.update(executable_sha256=sha(exe), ggml_sha256=sha(lib))
        for mode in CASES:
            data = json.loads((run([exe, mode], mode) / "stdout").read_text())
            r["arms"][mode] = data
            verify(data, mode)
        check(
            sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) < 80 << 20, "output budget"
        )
        r["scope_final"] = observe()
        r["status"] = "PASS_C291_LAST_READER_ALIAS_FIXTURE"
    except Exception as error:
        r["error"] = f"{type(error).__name__}: {error}"
    r["wall_s"] = round(time.monotonic() - start, 3)
    path = out / "receipt.tmp"
    path.write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    os.replace(path, out / "receipt.json")
    print(r["status"], r.get("error", ""), r["wall_s"], flush=True)
    return r["status"].startswith("FAIL")


if __name__ == "__main__":
    sys.exit(main())
