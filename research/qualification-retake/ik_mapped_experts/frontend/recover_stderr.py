"""Recover the original diagnostic bytes by checking the immutable SHA of each run."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from stderr_check import classify

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def recover(diag, prior_dirs, dest):
    os.umask(0o077)
    dest.mkdir(mode=0o700)
    message = rb"(CPU: using device CPU - )(\d+)( MiB free\n)"
    anchor = json.loads((HERE / "evidence.json").read_bytes())
    sample = (diag / "A/native.stderr").read_bytes()
    other = (diag / "B/native.stderr").read_bytes()
    a, b = re.match(message, sample), re.match(message, other)
    if not a or not b or sample[a.end() :] != other[b.end() :]:
        raise ValueError("unsupported stderr geometry")
    targets = {}
    for path, expected in zip(prior_dirs, anchor["runs"], strict=True):
        body = (path / "receipt.json").read_bytes()
        if sha(body) != expected["receipt_sha256"]:
            raise ValueError("unsealed historical receipt")
        targets[json.loads(body)["stderr_sha256"]] = path.name
    results = []
    rest = a[3] + sample[a.end() :]
    for mib in range(65537):
        buf = a[1] + str(mib).encode("ascii") + rest
        h = sha(buf)
        if h in targets:
            name = targets.pop(h)
            (dest / (name + ".stderr")).write_bytes(buf)
            results.append(
                {"run": name, "reported_cpu_free_mib": mib, "stderr_bytes": len(buf), "sha256": h}
            )
        if not targets:
            break
    if targets:
        raise ValueError("historical hashes unrecovered")
    report = dict(
        status="PASS_HISTORICAL_STDERR_HASH_RECONSTRUCTION",
        recovered=sorted(results, key=lambda r: r["run"]),
        witness_sha256=[sha(sample), sha(other)],
        suffix_sha256=sha(sample[a.end() :]),
        original_replacement="decimal CPU MiB free on first line only",
        witness_suffix_comparison=classify(sample[a.end() :], other[b.end() :]),
    )
    (dest / "receipt.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("diagnostic", type=Path)
    p.add_argument("r01", type=Path)
    p.add_argument("r02", type=Path)
    p.add_argument("new_output_dir", type=Path)
    a = p.parse_args()
    recover(a.diagnostic, (a.r01, a.r02), a.new_output_dir)
