"""Compare A and B on the same pinned C305 manager and prescribed service clocks."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL = HERE.parent / "manager"
SPEC = importlib.util.spec_from_file_location("tesy_c305_manager_runner", CONTROL / "run.py")
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)
from verify import compare_family, verify_arm, verify_fault  # noqa: E402

BUILD_FILES = (
    "fixture.cpp",
    "continuation.patch",
    "protocolo.md",
    "verify.py",
    "run.py",
)


def git(*args):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(HERE), *args], timeout=15, text=True
    ).strip()


def build(backend, dso, output, receipt):
    control.require(control.sha(dso) == control.BASE_DSO, "unexpected CPU ggml-base")
    tree = output / "backend"
    control.checkout_sources(backend, tree)
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(output),
        "LC_ALL": "C",
        "GIT_CEILING_DIRECTORIES": str(output),
        "MALLOC_ARENA_MAX": "2",
        "OMP_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": str(dso.parent),
    }

    def phase(name, command, directory=output):
        receipt["phases"][name] = control.run_bounded(command, output, name, env, cwd=directory)

    sources = tree / "src"
    phase("observe", ["git", "apply", CONTROL / "observer.patch"], tree)
    # The compiler must see the exact observed source qualified by confirm01.
    for name, expected in {
        "llama-moe-stream.cpp": "a17b9ac04c579f5ad82ad0920ec16dbb11adbd7cb89a1e2e5b2abe49026a6c03",
        "c294-service-window.h": "24fb0ee6cc91fefa0c10f8572f9f23bc16a86ae63e70c420d6bc5e3671995968",
    }.items():
        control.require(control.sha(sources / name) == expected, "observed C305 source mismatch")
    phase("candidate", ["git", "apply", HERE / "continuation.patch"], tree)
    phase("compiler", ["g++", "--version"])
    executable = output / "manager-ab"
    includes = (HERE, CONTROL, sources, tree / "include", tree / "ggml/include")
    phase(
        "build",
        [
            "g++",
            "-std=c++17",
            "-pthread",
            "-O0",
            "-g0",
            "-Wall",
            "-Wextra",
            "-ffunction-sections",
            "-fdata-sections",
            *["-I" + str(p) for p in includes],
            HERE / "fixture.cpp",
            sources / "llama-moe-stream.cpp",
            sources / "llama-impl.cpp",
            sources / "llama-mmap.cpp",
            "-Wl,--gc-sections",
            "-Wl,--wrap=pread",
            dso,
            "-lz",
            "-o",
            executable,
        ],
    )
    phase("linkage", ["ldd", executable])
    libs = (output / "linkage.out").read_text()
    resolved = [line for line in libs.splitlines() if "libggml-base.so" in line]
    control.require(
        len(resolved) == 1
        and "=>" in resolved[0]
        and control.sha(Path(resolved[0].split("=>")[1].split()[0])) == control.BASE_DSO
        and not any(x in libs.lower() for x in ("not found", "cuda", "nvidia", "libllama")),
        "runtime dependencies",
    )
    receipt["build"] = {
        "compiler": (output / "compiler.out").read_text().splitlines()[0],
        "compiler_sha256": control.sha(Path(shutil.which("g++", path=env["PATH"]))),
        "cpu_dso_sha256": control.BASE_DSO,
        "binary_sha256": control.sha(executable),
        "patched_manager_sha256": control.sha(sources / "llama-moe-stream.cpp"),
    }
    return executable, env


def measure(backend, dso, output, exploratory):
    # An existing output is never opened, including in error paths.
    output.mkdir()
    receipt = {
        "schema": "tesy-c305-producer-continuation-v1",
        "decision": "FAIL",
        "arms": [],
        "faults": [],
        "phases": {},
    }
    try:
        clean = not git("status", "--porcelain=v1", "--untracked-files=normal")
        receipt.update(
            tesy={
                "head": git("rev-parse", "HEAD"),
                "tree": git("rev-parse", "HEAD^{tree}"),
                "clean": clean,
            },
            backend={"commit": control.PIN, "tree": control.TREE},
            exploratory=exploratory,
        )
        control.require(exploratory or clean, "confirmation requires a clean checkout")
        files = [HERE / name for name in BUILD_FILES]
        files.extend(sorted(HERE.glob("*.h")))
        files.extend(
            CONTROL / name
            for name in (
                "fixture.cpp",
                "fixture_observer.h",
                "observer.patch",
                "run.py",
                "verify_result.py",
            )
        )
        receipt["files"] = {str(p.relative_to(HERE.parent)): control.sha(p) for p in files}
        exe, env = build(backend, dso, output, receipt)
        source = output / "synthetic.bin"
        receipt["input"] = control.generate(source)

        def run_arm(mode, schedule, name):
            arm = output / name
            arm.mkdir()
            usage = control.run_bounded([exe, mode, schedule, source, arm], output, name, env)
            raw_bytes = (arm / "raw.json").read_bytes()
            raw = json.loads(raw_bytes)
            return (
                arm,
                raw,
                {
                    "arm": name,
                    "mode": mode,
                    "schedule": schedule,
                    "usage": usage,
                    "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                },
            )

        for schedule in ("early", "late"):
            for index, mode in enumerate("ABBA", 1):
                arm, raw, entry = run_arm(mode, schedule, f"{schedule}-{index}-{mode}")
                result = verify_arm(raw, mode, schedule, arm)
                entry["result"] = result
                receipt["arms"].append(entry)
        receipt["comparison"] = compare_family([entry["result"] for entry in receipt["arms"]])
        for case in ("fault", "stale"):
            _, raw, entry = run_arm("B", case, f"negative-{case}")
            entry["result"] = verify_fault(raw, case)
            receipt["faults"].append(entry)
        receipt["decision"] = receipt["comparison"]["decision"]
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        receipt["allocated_bytes_before_receipt"] = control.tree_bytes(output)
        with tempfile.NamedTemporaryFile("w", dir=output, delete=False) as tmp:
            json.dump(receipt, tmp, indent=2, allow_nan=False)
            tmp.write("\n")
        os.replace(tmp.name, output / "receipt.json")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--ggml-base", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    parser.add_argument(
        "--exploratory", action="store_true", help="permit a dirty development checkout"
    )
    args = parser.parse_args()
    print(
        measure(
            args.backend.resolve(),
            args.ggml_base.resolve(),
            args.new_output_dir.resolve(),
            args.exploratory,
        )["decision"]
    )
