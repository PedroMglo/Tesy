"""Reopen the frozen gate and retain its diagnostic stderr in two new private directories."""

import argparse
import difflib
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "run.py"
SHA = "7eaf0620ea0f85acdd4e4d68346d3b8b9a3ee54091160fa00d695100c7cf68bf"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def classify(a, b):
    """Record a cause only if replacing this class makes all remaining bytes identical."""
    rules = {
        "hexadecimal_addresses": rb"0x[0-9A-Fa-f]+",
        "decimal_durations_with_unit": rb"\b\d+(?:\.\d+)?(?=\s*(?:ms|us|ns|s)\b)",
        "absolute_clock": rb"\b\d\d:\d\d:\d\d(?:\.\d+)?\b",
    }
    if a == b:
        return "identical"
    for name, pattern in rules.items():
        if re.sub(pattern, b"[value]", a) == re.sub(pattern, b"[value]", b):
            return name
    return "other_unclassified"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args, command = p.parse_known_args()
    if not command or command[0] != "verify" or "--new-output-dir" in command:
        p.error("supply the original verify arguments, excluding the output directory")
    os.umask(0o077)
    root = args.out.resolve()
    root.mkdir(mode=0o700)
    if digest(PROGRAM.read_bytes()) != SHA:
        raise ValueError("frozen verification code")
    real_run = subprocess.run
    logs = []
    for label in ("A", "B"):
        dest = root / label

        def retain(*argv, destination=dest, **kwargs):
            result = real_run(*argv, **kwargs)
            if "preexec_fn" in kwargs and "input" in kwargs:
                (destination / "native.stderr").write_bytes(result.stderr)
            return result

        sys.argv = [str(PROGRAM), *command, "--new-output-dir", str(dest)]
        with patch.object(subprocess, "run", retain):
            try:
                runpy.run_path(str(PROGRAM), run_name="__main__")
            except SystemExit as status:
                if status.code != 0:
                    raise RuntimeError("delegate verification failed") from None
        raw = (dest / "native.stderr").read_bytes()
        receipt = json.loads((dest / "receipt.json").read_bytes())
        if receipt["stderr_sha256"] != digest(raw):
            raise ValueError("stderr digest")
        logs.append(raw)
    a, b = logs
    classes = {}
    rows = []
    for tag, i, j, k, m in difflib.SequenceMatcher(
        None, a.splitlines(keepends=True), b.splitlines(keepends=True), autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        rows.append({"a_line": i + 1, "a_count": j - i, "b_line": k + 1, "b_count": m - k})
        name = classify(
            b"".join(a.splitlines(keepends=True)[i:j]), b"".join(b.splitlines(keepends=True)[k:m])
        )
        classes[name] = classes.get(name, 0) + 1
    report = dict(
        status="OBSERVED_DIAGNOSTIC_STDERR",
        whole_log_class=classify(a, b),
        changes=rows,
        groups_per_class=classes,
        stderr_sha256=list(map(digest, logs)),
        stderr_bytes=list(map(len, logs)),
        verified_source_sha256=SHA,
    )
    (root / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
