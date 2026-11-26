"""Diagnose boundary pages on the sealed GGUF without a forward or GPU allocation."""

import argparse
import ctypes as ct
import json
import mmap
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
T = run_path(str(HERE / "transfer.py"))
G = run_path(str(HERE / "grade.py"))
PAGE, require = T["PAGE"], T["require"]


def rounded(tensor, alignment):
    start = tensor["start"] // alignment * alignment
    end = (tensor["start"] + tensor["bytes"] + alignment - 1) // alignment * alignment
    return start, end - start


def observe(fd, size, tensors):
    base = T["file_map"](None, size, mmap.PROT_READ, mmap.MAP_SHARED, fd, 0)
    require(base not in (None, ct.c_void_p(-1).value), "file mmap")
    try:
        result = {}
        for role, t in tensors.items():
            start, n = rounded(t, PAGE)
            vec = (ct.c_ubyte * (n // PAGE))()
            require(T["mincore"](base + start, n, vec) == 0, "mincore")
            indices = [i for i, b in enumerate(vec) if b & 1]
            result[role] = dict(
                resident=len(indices), tensor_pages=len(vec), first=indices[:16], last=indices[-16:]
            )
        return result
    finally:
        require(T["unmap"](base, size) == 0, "munmap")


def run(reference):
    require(G["digest"](reference) == G["LAYER_REFERENCE"], "sealed layer")
    ref = json.loads(reference.read_bytes())
    with open(ref["model"], "rb", buffering=0) as f:
        fd = f.fileno()
        require(T["model_id"](fd) == ref["model_stat"], "source")
        size = ref["model_stat"][2]
        tensors = ref["tensors"]
        samples = {"initial": observe(fd, size, tensors)}
        evictions = {}
        for alignment in (PAGE, 2 << 20):
            spans = {role: rounded(t, alignment) for role, t in tensors.items()}
            for start, length in spans.values():
                os.posix_fadvise(fd, start, length, os.POSIX_FADV_DONTNEED)
            evictions[str(alignment)] = spans
            samples[str(alignment)] = observe(fd, size, tensors)
        require(T["model_id"](fd) == ref["model_stat"], "source drift")
    return dict(
        status="DIAGNOSTIC_ONLY",
        reference_sha256=G["LAYER_REFERENCE"],
        stat=ref["model_stat"],
        spans=evictions,
        samples=samples,
        admits_new_family=all(row["resident"] == 0 for row in samples[str(2 << 20)].values()),
        payload_read_B=0,
        model_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = run(a.reference)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=str(exc))
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("admits_new_family", r.get("reason", "")))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
