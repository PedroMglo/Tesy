"""Translate the two packed client deficits into mean net savings per eligible CPU layer."""

import argparse
import json
import re
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SOURCE = run_path(HERE / "screen.py")
QUAL, sha, need = (SOURCE[k] for k in ("QUAL", "sha", "need"))
PLACEMENT = re.compile(rb"load_tensors: layer +([0-9]+) assigned to device (CPU|CUDA0),")


def assess(archive):
    path = HERE / "receipt.json"
    need(
        sha(path) == "11f3ab3e7dba55b558fd77be1cf1430f7dd328d8880f8477f40ac32c23dffd9b",
        "budget receipt",
    )
    budgets = json.loads(path.read_bytes())
    results = {}
    for key, (part, run, _) in SOURCE["ARMS"].items():
        arm = budgets["arms"][key]
        root = archive / f"part-{part}"
        mf = root / "manifest.json"
        need(sha(mf) == arm["archive_manifest_sha256"], "manifest")
        directory = f"tesy-c281-{key}-natural-20261125-{run}/P/raw"
        rel = f"{directory}/tesy-c281-nvme-{key}-20261125-{run}-p.stderr"
        info = json.loads(mf.read_bytes())["files"][rel]
        log = root / rel
        need(log.stat().st_size == info["bytes"] and sha(log) == info["sha256"], "server log")
        placement = [(int(n), dev) for n, dev in PLACEMENT.findall(log.read_bytes()) if int(n) < 36]
        expected = [(i, b"CPU" if i < 25 else b"CUDA0") for i in range(36)]
        need(placement == expected, "36 repeating layers")
        steps = arm["budgets"]["sample"]["steps"]
        need(steps == 44, "first-final position")
        results[key] = {
            "first_final_44_steps_x_25_cpu_mean_ns": (arm["first_final_ns"] - 10**10)
            / (steps * 25),
            "decode_46_steps_x_25_cpu_mean_ns": arm["native_excess_ns_for_six_tok_s"] / (46 * 25),
            "stderr_sha256": info["sha256"],
        }
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    print(json.dumps(assess(parser.parse_args().archive), indent=2, sort_keys=True))
