"""Verify a sealed Tesy local raw archive against the published receipt."""

import argparse
import hashlib
import json
import stat
from pathlib import Path


def verify(archive, receipt):
    part = archive / receipt["part"]
    manifest = part / "manifest.json"

    def identity(path):
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("expected regular file")
        with path.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        return {"bytes": path.stat().st_size, "sha256": digest}

    if archive.name != receipt["archive_id"] or identity(manifest) != receipt["manifest"]:
        raise ValueError("archive or manifest identity differs")
    data = json.loads(manifest.read_text())
    if data["part"] != part.name or data["schema"] != "tesy-private-raw-archive-v1":
        raise ValueError("archive schema/part differs")
    for key, recorded in data["files"].items():
        rel = Path(key)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("invalid archive member")
        path = part / rel
        if path.resolve() != part.resolve() / rel or identity(path) != recorded:
            raise ValueError(f"raw mismatch: {rel}")
    for key in data["directories"]:
        if not stat.S_ISDIR((part / key).lstat().st_mode):
            raise ValueError("missing original directory")
    count = len(data["files"])
    size = sum(row["bytes"] for row in data["files"].values())
    if (count, size) != (receipt["file_count"], receipt["bytes"]):
        raise ValueError("archive accounting differs")
    return count, size


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    count, size = verify(args.archive, json.loads(args.receipt.read_text()))
    print(f"PASS {count} files, {size} bytes")
