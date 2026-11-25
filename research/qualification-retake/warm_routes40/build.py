"""Client-only C294 overlay and compiled GGML scheduler fixture. No model interface."""

import argparse
import hashlib
import json
import resource
import shutil
import subprocess
import time
from pathlib import Path

from witness import fixture, require

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "prefix_build/attempt-01/receipt.json"
BASE_SHA = "b5bccd6b296d9d12ebd92cbfb9cb1404495b62f742b59d0473e29fae288f8604"
CLIENT_PARENT_SHA = "56453afa712621d8bd5bbd532cf12efae50b99d0e08c04091a1e45f0a3261044"


def sha(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def limit():
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 2**20, 1536 * 2**20))


def build(parent, ggml, out, receipt):
    out.mkdir(mode=0o700)
    receipt.mkdir()
    result = {"status": "FAIL", "stages": [], "model_forwards": 0, "gpu_work": 0}
    started = time.monotonic()

    def run(label, cmd, expected=0):
        begin = time.monotonic()
        r = subprocess.run(
            list(map(str, cmd)),
            cwd=out,
            env={
                "PATH": "/usr/bin:/bin",
                "CUDA_VISIBLE_DEVICES": "",
                "OMP_NUM_THREADS": "1",
                "LC_ALL": "C",
            },
            capture_output=True,
            timeout=90,
            preexec_fn=limit,
        )
        (out / (label + ".log")).write_bytes(r.stdout + r.stderr)
        result["stages"].append(
            {
                "name": label,
                "returncode": r.returncode,
                "seconds": round(time.monotonic() - begin, 4),
                "log_sha256": sha(out / (label + ".log")),
            }
        )
        require(r.returncode == expected, f"{label} returned {r.returncode}; expected {expected}")
        return r.stdout

    try:
        require(sha(BASE) == BASE_SHA, "parent receipt")
        gold = json.loads(BASE.read_bytes())
        libs = parent / "cmake/bin"
        inc = parent / "source"
        require(
            sha(libs / "expert-service-window")
            == gold["products"]["expert-service-window"]["sha256"],
            "client parent",
        )
        for lib, h in gold["imported_ggml"].items():
            require(sha(ggml / lib) == h, "GGML " + lib)
        llama = libs / "libllama.so.0.0.9884"
        require(sha(llama) == gold["products"][llama.name]["sha256"], "libllama")
        src = parent / "project/tools"
        require(
            sha(src / "expert_service_window.cpp") == CLIENT_PARENT_SHA
            and sha(src / "block_native_run.cpp")
            == gold["pinned_client_sources"]["tools/block_native_run.cpp"],
            "sources",
        )
        for source in (
            src / "expert_service_window.cpp",
            src / "block_native_run.cpp",
            HERE / "routed_witness.h",
            HERE / "graph_fixture.cpp",
        ):
            shutil.copyfile(source, out / source.name)
        run("patch", ["/usr/bin/patch", "-p1", "--fuzz=0", "--batch", "-i", HERE / "client.patch"])
        flags = [
            "/usr/bin/c++",
            "-O2",
            "-DNDEBUG",
            "-std=gnu++17",
            "-pthread",
            f"-ffile-prefix-map={out}=/tesy-routed-client",
            f"-I{inc}/src",
            f"-I{inc}/include",
            f"-I{inc}/ggml/include",
            f"-I{inc}/vendor/nlohmann",
        ]
        ggml_link = [f"-Wl,-rpath,{ggml}", ggml / "libggml-cpu.so", ggml / "libggml-base.so"]
        run("fixture-compile", [*flags, "graph_fixture.cpp", "-o", "graph-fixture", *ggml_link])
        executable = out / "graph-fixture"
        passes = {}
        for name, rc in (
            ("normal", 0),
            ("pruned-entirely", 0),
            ("omit-layer", 1),
            ("wrong-position", 1),
            ("wrong-output", 1),
            ("swapped-ranks", 0),
            ("swapped-rows", 0),
        ):
            dest = out / (name + ".bin")
            run("fixture-" + name, [executable, name, dest], rc)
            if rc:
                require(not dest.exists(), "failed graph published journal")
                continue
            if name in {"normal", "pruned-entirely"}:
                passes[name] = fixture(dest.read_bytes())
            else:
                try:
                    fixture(dest.read_bytes())
                except ValueError as exc:
                    require(str(exc) == "label/position/rank mismatch", "wrong rejection")
                    passes[name] = "REJECTED_BY_INDEPENDENT_RANK_REFERENCE"
                else:
                    raise ValueError("mutant accepted")
        result["fixture"] = passes
        flags.extend(
            [
                "-DGGML_BACKEND_SHARED",
                "-DGGML_SHARED",
                "-DGGML_USE_CPU",
                "-DGGML_USE_CUDA",
                "-DLLAMA_SHARED",
            ]
        )
        new = out / "expert-service-window"
        run(
            "client-compile",
            [
                *flags,
                "expert_service_window.cpp",
                "-o",
                new,
                f"-Wl,-rpath,{libs}",
                llama,
                ggml / "libggml.so",
                *ggml_link,
                ggml / "libggml-cuda.so",
            ],
        )
        ldd = run("client-ldd", ["/usr/bin/ldd", new]).decode()
        loaded = {}
        for line in ldd.splitlines():
            words = line.split()
            if (
                len(words) >= 3
                and words[1] == "=>"
                and words[0].startswith(("libggml", "libllama"))
            ):
                path = Path(words[2]).resolve(strict=True)
                loaded[path.name] = sha(path)
        expected = dict(gold["imported_ggml"])
        expected[llama.name] = sha(llama)
        require(loaded == expected, "unexpected linked DSO identities")
        run("selftest", [new, "--self-test"])
        probe = json.loads(run("no-model-probe", [new, "--prefix-config-probe"]))
        require(
            not probe["enabled"] and probe["worker_count"] == probe["open_model_files"] == 0,
            "probe opened work",
        )
        result.update(
            status="PASS_GGML_CPU_FIXTURE_AND_CLIENT_ONLY",
            client_sha256=sha(new),
            common_libs_sha256=loaded,
            fixture_executable_sha256=sha(executable),
            parent_receipt_sha256=BASE_SHA,
            source_hashes={
                n: sha(HERE / n)
                for n in (
                    "routed_witness.h",
                    "graph_fixture.cpp",
                    "client.patch",
                    "protocol.md",
                    "build.py",
                    "witness.py",
                )
            },
        )
    except Exception as exc:
        result["error"] = str(exc)
        raise
    finally:
        result["elapsed_s"] = round(time.monotonic() - started, 3)
        result["max_child_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        result["private_files_bytes"] = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
        with (receipt / "receipt.json").open("x") as handle:
            json.dump(result, handle, sort_keys=True, indent=2)
            handle.write("\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for n in ("parent-build", "ggml-bin", "new-workspace", "new-receipt"):
        ap.add_argument("--" + n, type=Path, required=True)
    a = ap.parse_args()
    build(
        a.parent_build.resolve(),
        a.ggml_bin.resolve(),
        a.new_workspace.resolve(),
        a.new_receipt.resolve(),
    )
