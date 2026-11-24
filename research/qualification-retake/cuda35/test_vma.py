"""Exercise the VMA identity without loading an ELF via the dynamic loader or using CUDA."""

import hashlib
import json
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

from vma_identity import Reference, same_vma


def child(table):
    with ExitStack() as stack:
        refs = [Reference(stack, name, digest) for name, digest in table]
        print(json.dumps([ref.key for ref in refs]))


def run(table):
    with ExitStack() as stack:
        refs = [Reference(stack, name, digest) for name, digest in table]
        data = subprocess.check_output(
            [sys.executable, "-B", __file__, "--child", json.dumps(table)], text=True, timeout=45
        )
        keys = json.loads(data)
        for ref, key in zip(refs, keys, strict=True):
            same_vma(ref.key, tuple(key))
            ref.verify()
        work = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        a, b = work / "a", work / "b"
        for f in (a, b):
            f.write_bytes(b"same content")
        digest = hashlib.sha256(a.read_bytes()).hexdigest()
        left = Reference(stack, a, digest)
        right = Reference(stack, b, digest)
        try:
            same_vma(right.key, left.key)
        except ValueError:
            print(
                json.dumps(
                    {
                        "same_fd_content_passive_parent_child": len(keys),
                        "same_bytes_different_inode": "REJECTED",
                        "gpu_calls": 0,
                        "target_file_opens": 0,
                    }
                )
            )
            return
        raise AssertionError("accepted the wrong inode")


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(json.loads(sys.argv[2]))
    else:
        run(json.loads(Path(sys.argv[1]).read_text()))
