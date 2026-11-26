"""Install the locked Tesy GGUF on internal NVMe, preserving the original USB file."""

import argparse
import hashlib
import json
import mmap
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from host_readiness import BLOCK, FROZEN_SIZE, digest_direct, inventory, same_file  # noqa: E402

DIGEST = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
NAME = "gpt-oss-120b-MXFP4.gguf"


def transport(path):
    dev = (
        subprocess.check_output(
            ["findmnt", "--first-only", "-T", str(path.resolve()), "-no", "SOURCE"], text=True
        )
        .strip()
        .split("[")[0]
    )
    return set(subprocess.check_output(["lsblk", "-nrs", "-o", "TRAN", dev], text=True).split())


def sync_dir(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def place(alias, dest, receipt):
    original = alias.resolve(strict=True)
    source = original / NAME
    if not alias.is_symlink() or transport(source) != {"usb"}:
        raise ValueError("expected the current project alias to resolve to the USB source")
    if dest.parent != alias.parent or transport(dest.parent) != {"nvme"}:
        raise ValueError("expected a sibling directory on internal NVMe")
    free = shutil.disk_usage(dest.parent).free
    if free < FROZEN_SIZE + 32 * 2**30 or source.stat().st_size != FROZEN_SIZE:
        raise ValueError("insufficient space or unexpected original size")
    dest.mkdir(mode=0o700)
    start = time.monotonic()
    copied = 0
    h = hashlib.sha256()
    target = dest / NAME
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_DIRECT), "rb", buffering=0) as src:
        identity = same_file(os.fstat(src.fileno()))
        with (
            target.open("xb", buffering=0) as out,
            mmap.mmap(-1, BLOCK) as buf,
            memoryview(buf) as view,
        ):
            while copied < FROZEN_SIZE:
                n = os.readv(src.fileno(), [view])
                if n != min(BLOCK, FROZEN_SIZE - copied):
                    raise OSError("short read from original")
                if out.write(view[:n]) != n:
                    raise OSError("short write to destination")
                h.update(view[:n])
                copied += n
                if copied % (128 * 2**20) == 0:
                    os.fdatasync(out.fileno())
                    os.posix_fadvise(
                        out.fileno(), copied - 128 * 2**20, 128 * 2**20, os.POSIX_FADV_DONTNEED
                    )
            os.fsync(out.fileno())
        if identity != same_file(os.fstat(src.fileno())) or identity != same_file(source.stat()):
            raise ValueError("original changed during copy")
    if h.hexdigest() != DIGEST:
        raise ValueError("original digest mismatch")
    copy_s = time.monotonic() - start
    sync_dir(dest)
    verified = digest_direct(target, FROZEN_SIZE, DIGEST)
    inventory.mounts({"model": target})
    if alias.resolve(strict=True) != original or same_file(source.stat()) != identity:
        raise ValueError("project alias or USB source changed before publication")
    new_link = dest / ".project-alias"
    new_link.symlink_to(dest)
    os.replace(new_link, alias)
    sync_dir(alias.parent)
    if not (alias / NAME).samefile(target):
        raise ValueError("published alias does not identify verified copy")
    inventory.mounts({"model": alias / NAME})
    data = {
        "status": "PASS_NVME_MODEL_PLACEMENT",
        "source_transport": "usb",
        "destination_transport": "nvme",
        "original": str(source),
        "working_copy": str(target),
        "launcher_path": str(alias / NAME),
        "source_sha256": h.hexdigest(),
        "source_size": copied,
        "usb_read_and_nvme_write_s": round(copy_s, 3),
        "destination_direct_reread": verified,
        "c55_launcher_mount_gate": "PASS",
        "free_before_bytes": free,
        "free_after_bytes": shutil.disk_usage(dest).free,
        "forwards": 0,
        "physical_energy_j": None,
    }
    with receipt.open("x") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("current_project_alias", type=Path)
    ap.add_argument("exclusive_nvme_directory", type=Path)
    ap.add_argument("new_receipt_dir", type=Path)
    a = ap.parse_args()
    a.new_receipt_dir.mkdir()
    try:
        print(
            json.dumps(
                place(
                    a.current_project_alias,
                    a.exclusive_nvme_directory,
                    a.new_receipt_dir / "receipt.json",
                )
            )
        )
    except Exception as exc:
        (a.new_receipt_dir / "FAIL.txt").write_text(str(exc) + "\n")
        raise
