"""Compile the qualified CPU0 driver with the rank-stage callback as its input TU."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "cpu/build.py"
BUILDER = "f0fa790f6532de9a3464624db28da35091c9d130df9ea4276ce31116183fa58b"
if hashlib.sha256(PARENT.read_bytes()).hexdigest() != BUILDER:
    raise ValueError("CPU0 build recipe changed")
spec = importlib.util.spec_from_file_location("qualified_shape1_build", PARENT)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)


def build(a, r):
    # Select this study as the source folder of the private builder instance.
    parent.HERE = HERE
    parent.build(a, r)
    r.update(status="PASS_CPU0_RANK_STAGES_BUILD", build_recipe_sha256=BUILDER)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("old-build", "libs", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    report = {"status": "FAIL_PRESERVED"}
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        build(a, report)
    except Exception as e:
        report.update(status="FAIL_PRESERVED", reason=repr(e))
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(report["status"], report.get("reason", ""))
    raise SystemExit(report["status"] == "FAIL_PRESERVED")
