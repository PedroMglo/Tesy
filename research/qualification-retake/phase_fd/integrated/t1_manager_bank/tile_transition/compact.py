"""Recheck all four first-decode receipts and preserve the separate build failure."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
assess = run_path(str(HERE / "review.py"))
need = assess["require"]
PINS = (
    "3661c5cb80a73d33739734338ab020b73be484f4110a1fa1698245a5f2ab28cc",
    "18eedc6035445c59b1e27845df5412dea2260b70c30f27224a8025635e1577d5",
)


def load(path, pin):
    contents = path.read_bytes()
    need(hashlib.sha256(contents).hexdigest() == pin, "receipt digest " + path.name)
    return json.loads(contents)


def compact(r1, r2):
    failed, passed = (load(d / "receipt.json", pin) for d, pin in zip((r1, r2), PINS, strict=True))
    need(failed["status"] == "FAIL_PRESERVED" and not failed["arms"], "untouched failure")
    stderr = (r1 / "build-tile-transition/stderr").read_bytes()
    need(
        hashlib.sha256(stderr).hexdigest()
        == "75596fed85ca2e8f304ccd06108c2d1f7c701b1a8b9705d1e7a6e2957f77c9cd"
        and b"'llama_moe_stream_layer' was not declared" in stderr,
        "expected missing dependency",
    )
    need(passed["status"] == "PASS_C291_TILE_TRANSITION_CPU_FAMILY", "closed family")
    gold = load(r2 / "gold.json", passed["gold_sha256"])
    rows = {
        arm: load(r2 / ("case-" + arm) / "raw.json", meta["raw_sha256"])
        for arm, meta in passed["arms"].items()
    }
    checks = assess["family"](rows, gold)
    need(checks == passed["verified"], "replayed oracle")
    commands = passed["commands"]
    scope = passed["scope_final"]
    need(
        scope["memory.swap.max"] == scope["memory.swap.current"] == 0
        and scope["memory.peak"] <= scope["memory.max"] == 2**30
        and not any(scope["memory.events"].values()),
        "CPU resources",
    )
    return {
        "status": passed["status"],
        "verified": checks,
        "first_decode_ids": rows["bank"]["decode_ids"],
        "fail_preserved": {
            "receipt_sha256": PINS[0],
            "failed_stage": "compiler include order",
            "wall_s": failed["commands"]["build-tile-transition"]["wall_s"],
            "commit": failed["commit"],
        },
        "passed": {
            "receipt_sha256": PINS[1],
            "commit": passed["commit"],
            "tree": passed["tree"],
            "binary_sha256": passed["binary"]["sha256"],
            "raw_sha256": {arm: meta["raw_sha256"] for arm, meta in passed["arms"].items()},
        },
        "pack_bytes": gold["pack_bytes"],
        "synthetic_pack_sha256": gold["pack_sha256"],
        "scratch_bytes": rows["bank"]["scratch_bytes"],
        "capture_bytes": rows["bank"]["capture_bytes"],
        "command_wall_s": {k: v["wall_s"] for k, v in commands.items()},
        "memory_peak_bytes": scope["memory.peak"],
        "swap_bytes": 0,
        "forward_120b": 0,
        "gpu_processes": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("failed", "passed", "new-output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    args.new_output.mkdir(mode=0o700)
    try:
        output = compact(args.failed, args.passed)
    except (OSError, ValueError, KeyError) as exc:
        (args.new_output / "receipt.json").write_text(
            json.dumps({"status": "FAIL_PRESERVED", "reason": str(exc)}) + "\n"
        )
        raise
    tmp = args.new_output / "receipt.tmp"
    tmp.write_text(json.dumps(output, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(args.new_output / "receipt.json")
