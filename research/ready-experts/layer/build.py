"""Compile the layer fixture against the sealed C269 CPU/base DSOs and C291 source closure."""

import argparse
import json
import os
import resource
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = HERE.parents[1] / "qualification-retake"
parent = run_path(Q / "igpu_resident_rank/projection/rank_split/build.py")["parent"]


def run(a):
    parent.HERE = HERE
    r = {}
    parent.build(a, r)
    r.update(status="PASS_READY_LAYER_BUILD", tree=parent.git("rev-parse", "HEAD^{tree}"))
    return r


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("old-build", "libs", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        result = run(a)
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": repr(exc)}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] != "PASS_READY_LAYER_BUILD")
