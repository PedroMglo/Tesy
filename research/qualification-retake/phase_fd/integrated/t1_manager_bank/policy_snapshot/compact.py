"""Regrade the eight C269 selector controls from their sealed local bytes without a build."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RAW_SHA = "e689fd19a7d78b5fb8833e63f761ebb2d46895953d970f534f1d4ea8dcb04264"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def compact(out):
    require = run_path(HERE / "review.py")["require"]
    require(sha(out / "receipt.json") == RAW_SHA, "family identity")
    src = json.loads((out / "receipt.json").read_bytes())
    require(
        src["status"] == "PASS_C269_POLICY_SNAPSHOT_FIXTURE_ONLY"
        and src["commit"] == "47d816018d670ecfe90d38cbe50b5ea4ee66e932"
        and src["model_forwards"] == src["gpu_calls"] == 0
        and src["sources"] == {k: sha(HERE / k) for k in src["sources"]}
        and src["protocol_sha256"] == sha(HERE / "protocol.md")
        and src["binary_sha256"] == sha(out / "policy-cpu")
        and src["header_sha256"] == sha(out / "private/phase-fd-integrated.h"),
        "source, binary or scope",
    )
    for arm, files in src["arms"].items():
        require(files == {p.name: sha(p) for p in (out / arm).iterdir()}, "arm bytes " + arm)
    # PFJ cut tuples become arrays when the acquisition receipt is published.
    verified = json.loads(json.dumps(run_path(HERE / "review.py")["family"](out), allow_nan=False))
    require(src["verified"] == verified, "integer oracle")
    result = {
        k: src[k]
        for k in (
            "status",
            "commit",
            "tree",
            "protocol_sha256",
            "prior_build_sha256",
            "compiler_sha256",
            "binary_sha256",
            "header_sha256",
            "build_s",
            "wall_s",
            "output_bytes",
            "scope_peak",
            "gpu_calls",
            "model_forwards",
        )
    }
    return dict(result, source_receipt_sha256=RAW_SHA, verified=verified)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = compact(a.family)
    except (ValueError, OSError, KeyError) as err:
        result = {"status": "FAIL_PRESERVED", "reason": str(err)}
    tmp = a.new_output_dir / "receipt.tmp"
    tmp.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
