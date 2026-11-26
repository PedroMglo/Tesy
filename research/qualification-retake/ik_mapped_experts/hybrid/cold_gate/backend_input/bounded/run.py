"""Compare bounded and roomy readers with a deliberately deferred consumer."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OLD = run_path(str(HERE.parent / "run.py"))
sha = OLD["sha"]
EXPECTED = [
    "DIRECT 8 3 4 3121",
    "DIRECT 2 4 4 3121",
    "PREAD_RANDOM 8 3 4 3121",
    "PREAD_RANDOM 2 4 4 3121",
    "FAULTS 2_STREAMS PARTIAL_ENQUEUE FENCE_FAILURE SHORT_READ",
]


def exercise(out):
    cc = Path("/usr/bin/g++").resolve()
    exe = out / "bounded-reader"
    cmd = [
        str(cc),
        "-std=c++17",
        "-O1",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fsanitize=undefined",
        "-fsanitize-undefined-trap-on-error",
        "-fno-sanitize-recover=all",
        str(HERE / "fixture.cpp"),
        "-o",
        str(exe),
    ]
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(out)}
    for args, log, seconds in ((cmd, "compiler.log", 30), ([exe], "fixture.log", 10)):
        with (out / log).open("xb") as f:
            subprocess.run(
                args,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=env,
                preexec_fn=OLD["limits"],
                check=True,
                timeout=seconds,
            )
    lines = (out / "fixture.log").read_text().splitlines()
    if lines != EXPECTED:
        raise ValueError("unexpected bytes, fences or failures")
    return dict(observed=lines, compiler_sha256=sha(cc), binary_sha256=sha(exe), compile_argv=cmd)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-output-dir", type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", model_starts=0, gpu_allocations=0, http_requests=0)
    try:
        git = ["git", "-C", HERE]
        head, tree = subprocess.check_output(
            [*git, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
        ).splitlines()
        if head != a.commit or subprocess.check_output([*git, "status", "--porcelain"]):
            raise ValueError("dirty or changed fixture")
        r.update(
            commit=head,
            tree=tree,
            sources={
                f: sha(HERE / f)
                for f in (
                    "run.py",
                    "protocol.md",
                    "fixture.cpp",
                    "bounded_input.hpp",
                    "../bank_input.hpp",
                )
            },
        )
        r.update(exercise(out), status="GO_NATIVE_CACHE_HOOK")
    except Exception as e:
        r["reason"] = f"{type(e).__name__}: {e}"
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
