"""Exercise the stock GGML CONT/reshape/GET_ROWS aliases without GPU or model."""

import argparse
import json
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE / "build.py"))


def run(a, out):
    src = a.source.resolve()
    obj = a.objects.resolve()
    rev = subprocess.check_output(
        ["git", "-C", src, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    B["need"](rev == [B["FRONT"]["PIN"], B["FRONT"]["TREE"]], "pin")
    lib = B["pin"](obj / "ggml/src/libggml.so", B["TINY"]["BASE"]["ggml/src/libggml.so"])
    exe = out / "views"
    subprocess.run(
        [
            "/usr/bin/g++-15",
            "-std=c++17",
            "-O1",
            "-I" + str(src / "ggml/include"),
            HERE / "test_rank_view.cpp",
            lib,
            "-o",
            exe,
        ],
        check=True,
        timeout=20,
    )
    env = B["FRONT"]["env"](obj)
    env["CUDA_VISIBLE_DEVICES"] = ""
    proc = subprocess.run([exe], env=env, text=True, capture_output=True, timeout=5)
    (out / "stdout").write_text(proc.stdout)
    (out / "stderr").write_text(proc.stderr)
    B["need"](
        proc.returncode == 0
        and proc.stdout.splitlines()
        == [
            "PASS_VIEW width=32 ids=128 logical_pitch=32 physical_pitch=16",
            "PASS_VIEW width=1 ids=4 logical_pitch=32 physical_pitch=16",
        ],
        "native rank/gather/bounds",
    )
    return dict(
        status="PASS_CPU_GGML_RANK_VIEW_FIXTURE",
        binary_sha256=B["sha"](exe),
        ggml_sha256=B["sha"](lib),
        source_sha256=B["sha"](HERE / "test_rank_view.cpp"),
        header_sha256=B["sha"](HERE / "rank_view.hpp"),
        widths=[32, 1],
        words_checked=132,
        model_loads=0,
        gpu_dispatches=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "objects", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        r = run(a, out)
    except Exception as err:
        r = {"status": "FAIL_PRESERVED", "error": str(err)}
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"])
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
