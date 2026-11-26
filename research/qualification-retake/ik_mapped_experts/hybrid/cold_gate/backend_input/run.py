"""Build and exercise the deferred-consumer bank input, without weights or an accelerator."""

import argparse
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = ["DIRECT 3 4 3556 2 1 51 1", "PREAD_RANDOM 3 4 3556 2 1 51 1", "SHORT_READ 2 1 64"]


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 << 20, 32 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run(out, commit):
    head, tree = subprocess.check_output(
        ["git", "-C", HERE, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    if head != commit or subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]):
        raise ValueError("dirty or changed freeze")
    compiler = Path("/usr/bin/g++").resolve(strict=True)
    binary = out / "deferred-fill"
    argv = [
        str(compiler),
        "-std=c++17",
        "-O1",
        "-g",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fsanitize=undefined",
        "-fsanitize-undefined-trap-on-error",
        "-fno-sanitize-recover=all",
        str(HERE / "fixture.cpp"),
        "-o",
        str(binary),
    ]
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(out)}
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(
            argv,
            env=env,
            check=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=30,
            preexec_fn=limits,
        )
    with (out / "stdout").open("xb") as stdout, (out / "stderr").open("xb") as stderr:
        subprocess.run(
            [binary],
            env=env,
            check=True,
            stdout=stdout,
            stderr=stderr,
            timeout=10,
            preexec_fn=limits,
        )
    observed = (out / "stdout").read_text().splitlines()
    if observed != EXPECTED or (out / "stderr").stat().st_size:
        raise ValueError("unexpected conservation or runtime diagnostics")
    return dict(
        status="PASS_DEFERRED_BANK_INPUT_ONLY",
        commit=head,
        tree=tree,
        model_loads=0,
        requests=0,
        gpu_allocations=0,
        synthetic_file_B=16384,
        observed=observed,
        compiler=str(compiler),
        compiler_sha256=sha(compiler),
        compiler_version=subprocess.check_output([compiler, "--version"], text=True).splitlines()[
            0
        ],
        compile_argv=argv,
        binary_sha256=sha(binary),
        sources={
            f.name: sha(f)
            for f in (
                HERE / "bank_input.hpp",
                HERE / "fixture.cpp",
                HERE / "protocol.md",
                Path(__file__),
            )
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-output-dir", type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        r = run(out, a.commit)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=str(exc))
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
