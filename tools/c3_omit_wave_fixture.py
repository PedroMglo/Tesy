#!/usr/bin/env python3
"""Create a disposable capture with one real wave contribution removed."""

import csv
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: c3_omit_wave_fixture.py SOURCE_CAPTURE FIXTURE_ROOT")
    source = Path(sys.argv[1]).resolve()
    target = Path(sys.argv[2])
    if not source.is_dir() or target.exists():
        raise SystemExit("source missing or no-replace fixture root exists")
    rows = list(csv.DictReader((source/"index.tsv").open(),delimiter="\t"))
    subset = [r for r in rows if r["phase"] == "prefill0" and r["layer"] == "0"]

    def one(name):
        selected = [r for r in subset if r["name"] == name]
        if len(selected) != 1:
            raise ValueError(f"expected exactly one {name}")
        return selected[0]

    def raw(row):
        path = source/row["file"]
        if path.stat().st_size != int(row["bytes"]):
            raise ValueError("indexed payload size changed")
        return np.fromfile(path,dtype="<f4")

    downs = [r for r in subset if r["name"] == "ffn_moe_down_biased"]
    masks = [r for r in subset if r["name"] == "ffn_moe_wave_mask"]
    if len(downs) != len(masks) or len(downs) < 2:
        raise ValueError("multi-wave capture incomplete")
    selected_wave = None
    for wave,mask_row in enumerate(masks):
        mask = raw(mask_row).reshape(32,4)
        if np.count_nonzero(mask) > 0:
            selected_wave = wave
            break
    if selected_wave is None:
        raise ValueError("no active wave")
    weights = raw(one("ffn_moe_weights_softmax")).reshape(32,4)
    down = raw(downs[selected_wave]).reshape(32,4,2880)
    mask = raw(masks[selected_wave]).reshape(32,4)
    contribution = (down * mask[:,:,None] * weights[:,:,None]).sum(axis=1,dtype=np.float32)
    if not np.isfinite(contribution).all() or not np.any(contribution):
        raise ValueError("wave contribution empty or nonfinite")
    output_row = one("ffn_moe_out")
    original = raw(output_row).reshape(32,2880)
    mutated = np.asarray(original-contribution,dtype="<f4")
    if not np.isfinite(mutated).all() or np.array_equal(mutated,original):
        raise ValueError("omitted wave did not change FFN output")
    target.mkdir(mode=0o700)
    try:
        for path in source.iterdir():
            if path.is_file():
                (target/path.name).symlink_to(path.resolve())
        replacement = target/output_row["file"]
        replacement.unlink()
        with replacement.open("xb") as out:
            out.write(mutated.tobytes())
        manifest = {"schema":"c3-omitted-wave-fixture-v1", "classification":"SYNTHETIC_MUTANT",
                    "source_index_sha256":sha(source/"index.tsv"),
                    "source_output_sha256":sha(source/output_row["file"]),
                    "mutated_output_sha256":sha(replacement),
                    "selected_wave":selected_wave,
                    "active_pairs":int(np.count_nonzero(mask)),
                    "contribution_nonzero":int(np.count_nonzero(contribution)),
                    "contribution_max_abs":float(np.max(np.abs(contribution)))}
        with (target/"fixture.json").open("x") as out:
            json.dump(manifest,out,indent=2,allow_nan=False);out.write("\n")
        print(json.dumps(manifest,allow_nan=False))
    except Exception:
        # Leave any partial fixture as failed evidence; never change source files.
        raise


if __name__ == "__main__":
    main()
