#!/usr/bin/env python3
"""Read-only O_DIRECT full GGUF hash for launcher preflight, outside timed inference."""

import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import time


def verify(path, expected, expected_size):
    path=Path(path).resolve()
    before=path.stat()
    if before.st_size!=expected_size:
        raise ValueError("GGUF size differs from frozen model lock")
    if not hasattr(os,"O_DIRECT"):
        raise RuntimeError("O_DIRECT unavailable; no buffered fallback")
    flags=os.O_RDONLY|os.O_DIRECT|os.O_CLOEXEC
    fd=os.open(path,flags)
    buffer=mmap.mmap(-1,8*1024*1024)
    view=memoryview(buffer)
    digest=hashlib.sha256()
    total=0
    started=time.monotonic()
    try:
        while True:
            n=os.readv(fd,[view])
            if n==0:break
            digest.update(view[:n]);total+=n
    finally:
        view.release();buffer.close();os.close(fd)
    after=path.stat()
    if total!=expected_size or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) != \
       (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError("GGUF changed or short read during full verification")
    actual=digest.hexdigest()
    if actual!=expected:raise ValueError(f"GGUF SHA-256 differs: {actual}")
    return {"status":"PASS","path":str(path),"size_bytes":total,"sha256":actual,
            "read_mode":"O_DIRECT requested; no application fallback",
            "elapsed_s":time.monotonic()-started,
            "device":before.st_dev,"inode":before.st_ino,"mtime_ns":before.st_mtime_ns}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("path",type=Path)
    p.add_argument("--sha256",required=True)
    p.add_argument("--size",required=True,type=int)
    a=p.parse_args()
    print(json.dumps(verify(a.path,a.sha256,a.size),allow_nan=False))


if __name__=="__main__":main()
