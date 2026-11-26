"""Optional offline replay using an isolated copy of each historical raw directory."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


def reproduce(r01, r02, study):
    implementation = Path(__file__).with_name("compact_mixed.py")
    spec = importlib.util.spec_from_file_location("tesymixedcompact", implementation)
    comp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comp)
    roots = [r01, r02]
    blocked = tuple(str(r.absolute()) for r in roots)
    attempts = []

    def check(path):
        if isinstance(path, (str, bytes, os.PathLike)):
            value = os.fsdecode(path)
            if any(value == x or value.startswith(x + "/") for x in blocked):
                attempts.append(value)
                raise AssertionError("attempted live access to the original campaign")

    def safeguard(fn):
        def checked(path, *args, **kwargs):
            check(path)
            return fn(path, *args, **kwargs)

        return checked

    with tempfile.TemporaryDirectory(prefix="tesy-offline-proof-") as td:
        relocated = [Path(td) / n for n in ("r01-copy", "r02-copy")]
        for original, copy in zip(roots, relocated, strict=True):
            copy.mkdir()
            files = [
                "receipt.json",
                "pre.json",
                "run.json",
                "post.json",
                "telemetry.jsonl",
                "stdout.txt",
                "stderr.txt",
                "static-map.json",
                *(p.name for p in original.glob("loads.*")),
            ]
            for name in files:
                shutil.copyfile(original / name, copy / name)
            shutil.copytree(original / "native", copy / "native")
            assert not (copy / "driver").exists()
        # open()/io.open are covered by Python's audit event, and path lookups by the wrappers.
        sys.addaudithook(lambda event, args: check(args[0]) if event == "open" else None)
        result = {}
        with ExitStack() as stack:
            for name in ("stat", "lstat", "readlink", "listdir", "scandir", "access"):
                stack.enter_context(patch.object(os, name, safeguard(getattr(os, name))))
            for orig, copy in zip(("r01", "r02"), relocated, strict=True):
                blob = (
                    json.dumps(comp.compact(copy, study), sort_keys=True, indent=2, allow_nan=False)
                    + "\n"
                ).encode()
                result[orig] = hashlib.sha256(blob).hexdigest()
    assert not attempts
    assert result == {
        "r01": "2d4810f7f2d783a0d2fdcb27cbfdc89a285948b6723cb5459115b9f26f37e6d0",
        "r02": "8895db5086b272a6aadb31f2cb277c187dd9734f559836f5773691175c01ac4e",
    }
    return {
        "status": "PASS_RELOCATED_COPIES_ONLY_PERSISTENT_C269",
        "original_file_access_during_compaction": 0,
        "copied_private_symlinks": 0,
        "public_compact_sha256": result,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--r01", type=Path, required=True)
    p.add_argument("--r02", type=Path, required=True)
    p.add_argument("--study", type=Path, default=Path(__file__).resolve().parent)
    a = p.parse_args()
    print(json.dumps(reproduce(a.r01, a.r02, a.study), sort_keys=True, indent=2))
