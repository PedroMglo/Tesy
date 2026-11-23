#!/usr/bin/env python3
"""Make a no-replace checksum map for compact C3 review files in Git."""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SUPPORT_TOOLS = {
    "tools/c2_server_run.py", "tools/c2_gate.py", "tools/c2_publish_run.py",
    "tools/c2_latency_client.py", "tools/c2_launch_target.py", "tools/c2_stop_server.py",
    "tools/run_bounded.py", "tools/test_c2_gate.py",
}


def selected(path):
    if path in ("README.md", "LAB_STATE.md", "DECISIONS.md", "results/INDEX.md"):
        return True
    if path.startswith("research/C3-") and path.endswith(".md"):
        return True
    if path.startswith("workloads/c3_") and path.endswith(".json"):
        return True
    if path.startswith("tools/c3_") and path.endswith(".py"):
        return True
    if path.startswith("tools/test_c3_") and path.endswith(".py"):
        return True
    if path in SUPPORT_TOOLS:
        return True
    if path.startswith("results/c3-") and path.endswith(".json"):
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    names = sorted(name for name in tracked if name and selected(name) and
                   name != "results/c3-audit-index.json")
    rows = []
    for name in names:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing or linked review file: {name}")
        data = path.read_bytes()
        if name.startswith("results/") and len(data) > 250_000:
            raise ValueError(f"result too large for compact review: {name}")
        rows.append({"path": name, "bytes": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()})
    report = {"schema": "c3-compact-audit-index-v1",
              "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "branch": "campaign/c3-layer-reference-prefill-20260926-1800utc",
              "base_lab_commit": "81531d9dc33caddbbf07928106de47cfe2a6d42a",
              "target_gguf_sha256": "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
              "streaming_backend_sha": "1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5",
              "stock_backend_sha": "4b1a27fa0eb875bbca4f6cfe936e3d65adc685c0",
              "file_count": len(rows), "files": rows,
              "raw_policy": "model weights, builds, raw captures, SSE text and telemetry series remain local; compact publications index their SHA-256",
              "self_hash_excluded": True}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as out:
        json.dump(report, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({"output": str(output), "file_count": len(rows)}))


if __name__ == "__main__":
    main()
