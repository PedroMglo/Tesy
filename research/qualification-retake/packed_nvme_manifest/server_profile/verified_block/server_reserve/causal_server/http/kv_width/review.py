"""Regrade all saved finite attention vectors, inverted masks, providers and image controls."""

import argparse
import json
import math
import struct
from pathlib import Path
from runpy import run_path

X = run_path(str(Path(__file__).with_name("run.py")))
sha, need, save = (X[k] for k in ("sha", "need", "save"))
PINS = (
    "2600bbaf6fc77dcf32731f25cd4a0e72425dc4187533085f31e5d5766716debf",
    "c8362dd37d178f68351228341b3a6bf2c94e0a8149f01428a348c8b8f851d181",
    "000dd9c705f4e21279b66ec83fc6fda6eb492178c5b8110a1ea7edab848d6579",
    "fedce434aa0098ff4b3701260bdb0b41586f6c642a863003e1ec339e81c74978",
)


def review(folders):
    rs = [X["G"]["read"](p / "receipt.json", h) for p, h in zip(folders, PINS, strict=True)]
    built, fail, rebuild, passed = rs
    need(
        built["arms"] == rebuild["arms"]
        and rebuild["parent_build_sha256"] == PINS[0]
        and fail["status"] == "FAIL_PRESERVED"
        and fail["build_sha256"] == PINS[0]
        and passed["build_sha256"] == PINS[2]
        and passed["status"] == "GO_CUDA_WIDE_ATTENTION_OPERATOR",
        "sealed order",
    )
    for root, r in zip(folders, rs, strict=True):
        for f, h in r["files"].items():
            dest = root / f
            if not dest.exists() and dest.name == "libllama.so.0":
                alias = json.loads((dest.parent / "alias.json").read_bytes())
                need(
                    alias["alias"] == dest.name
                    and alias["target"] == X["G"]["IMAGE"]
                    and alias["sha256"] == h,
                    "archived symlink",
                )
                dest = dest.parent / alias["target"]
            need(sha(dest) == h, "changed raw file")
    rows = {}
    for n in X["WIDTHS"]:
        d = folders[-1] / "device" / str(n)
        ref = (d / "serial.f32").read_bytes()
        mut = (d / "mutant.f32").read_bytes()
        need(
            len(ref) == len(mut) == 49152
            and (d / "block.f32").read_bytes() == ref
            and all(math.isfinite(f) for b in (ref, mut) for (f,) in struct.iter_unpack("<f", b)),
            "finite complete vectors",
        )
        rows[str(n)] = [
            sum(ref[i : i + 4] != mut[i : i + 4] for i in range(j, j + 16384, 4))
            for j in (0, 16384, 32768)
        ]
        need(rows[str(n)] == passed["rows"][str(n)]["wrong_mask_different_by_row"], "mutant rows")
    for label in ("before", "after"):
        owners = json.loads((folders[-1] / (label + "-owners.json")).read_bytes())
        components = owners["observed"].split(", ")
        need(
            len(components) == 3
            and int(components[0]) == owners["fixture_pid"]
            and components[1] == passed["live"][label]["gpu"]["uuid"],
            "owner",
        )
    return dict(
        status=passed["status"],
        receipts_sha256=PINS,
        images=built["arms"],
        total_finite_equal_F32=5 * 3 * 4096,
        wrong_mask_different_by_row=rows,
        model_starts=0,
        candidate_image_builds=1,
        positive_operator_processes=1,
        initial_attempt=fail["error"],
        operator_s=passed["wall_s"],
        observed_vram_MiB={k: v["gpu"]["used_mib"] for k, v in passed["live"].items()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folders", nargs=4, type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", review(a.folders))
