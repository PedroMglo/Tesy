#!/usr/bin/env python3
"""Compare complete float32 logit rows from two fixed-prefix probe runs."""

import argparse
from array import array
import hashlib
import heapq
import json
import math
from pathlib import Path


def read_row(path):
    data = Path(path).read_bytes()
    if len(data) % 4:
        raise ValueError(f"non-float32 file size: {path}")
    row = array("f")
    row.frombytes(data)
    if not all(math.isfinite(x) for x in row):
        raise ValueError(f"non-finite logit: {path}")
    return data, row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("reference")
    p.add_argument("candidate")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    raw_a, row_a = read_row(a.reference)
    raw_b, row_b = read_row(a.candidate)
    if len(row_a) != len(row_b):
        raise ValueError("vocabulary length mismatch")
    diffs = [abs(float(x) - float(y)) for x, y in zip(row_a, row_b)]
    top_a = heapq.nlargest(10, range(len(row_a)), key=row_a.__getitem__)
    top_b = heapq.nlargest(10, range(len(row_b)), key=row_b.__getitem__)
    report = {
        "reference": a.reference,
        "candidate": a.candidate,
        "reference_sha256": hashlib.sha256(raw_a).hexdigest(),
        "candidate_sha256": hashlib.sha256(raw_b).hexdigest(),
        "n_logits": len(row_a),
        "bitwise_equal": raw_a == raw_b,
        "exact_equal_count": sum(x == y for x, y in zip(row_a, row_b)),
        "max_abs": max(diffs),
        "mean_abs": sum(diffs) / len(diffs),
        "rmse": math.sqrt(sum(x*x for x in diffs) / len(diffs)),
        "top1_reference": top_a[0],
        "top1_candidate": top_b[0],
        "top10_overlap": len(set(top_a) & set(top_b)),
    }
    Path(a.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
