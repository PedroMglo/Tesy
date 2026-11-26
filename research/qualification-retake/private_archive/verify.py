"""Verify a sealed Tesy local raw archive against the published receipt."""

import argparse
import hashlib
import json
import stat
from pathlib import Path


def identity(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("expected regular file")
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    return {"bytes": path.stat().st_size, "sha256": digest}


def verified_member(root, key, recorded):
    rel = Path(key)
    path = root / rel
    if rel.is_absolute() or ".." in rel.parts or path.resolve() != root.resolve() / rel:
        raise ValueError("unexpected archive path")
    if identity(path) != recorded:
        raise ValueError(f"raw mismatch: {rel}")


def verify(archive, receipt):
    part = archive / receipt["part"]
    manifest = part / "manifest.json"

    if archive.name != receipt["archive_id"] or identity(manifest) != receipt["manifest"]:
        raise ValueError("archive or manifest identity differs")
    data = json.loads(manifest.read_text())
    if data["part"] != part.name or data["schema"] != "tesy-private-raw-archive-v1":
        raise ValueError("archive schema/part differs")
    for key, recorded in data["files"].items():
        verified_member(part, key, recorded)
    for key in data["directories"]:
        if not stat.S_ISDIR((part / key).lstat().st_mode):
            raise ValueError("missing original directory")
    count = len(data["files"])
    size = sum(row["bytes"] for row in data["files"].values())
    if (count, size) != (receipt["file_count"], receipt["bytes"]):
        raise ValueError("archive accounting differs")
    return count, size


def verify_persistent(archive, receipt, project_root):
    # The caller verifies the sealed part, including this index, before resolving data.
    index = json.loads((archive / receipt["part"] / "persistent/index/index.json").read_text())
    if index["schema"] != "tesy-already-persistent-raw-index-v1":
        raise ValueError("unexpected persistent index")
    count = size = 0
    for group in index["groups"].values():
        location = Path(group["project_relative_root"])
        if location.is_absolute() or ".." in location.parts or location.parts[0] != "build":
            raise ValueError("invalid project artifact root")
        for key, record in group["files"].items():
            verified_member(project_root, location / Path(key), record)
        if group["count"] != len(group["files"]) or group["bytes"] != sum(
            v["bytes"] for v in group["files"].values()
        ):
            raise ValueError("persistent group accounting differs")
        count += group["count"]
        size += group["bytes"]
    return count, size


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Also verify the original persistent roots indexed in part-03",
    )
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    count, size = verify(args.archive, receipt)
    print(f"PASS {count} files, {size} bytes")
    if args.project_root is not None:
        count, size = verify_persistent(args.archive, receipt, args.project_root)
        print(f"PASS indexed original roots: {count} files, {size} bytes")
