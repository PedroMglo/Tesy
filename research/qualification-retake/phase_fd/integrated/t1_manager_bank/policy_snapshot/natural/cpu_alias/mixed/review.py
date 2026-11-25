"""Check complete CPU and CUDA values and localize the wrong generation."""

import hashlib
import json
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[6]
LEGACY = run_path(QUAL / "packed_cpu_mixed/run.py")
need = LEGACY["require"]
LABELS = ("dense_A", "dense_B", "original", "replacement", "restore", "wrong_pages")
WIDTH = 2880
N = 3
COUNT = 3 * N * 4 * WIDTH


def changes(a, b):
    need(len(a) == len(b) == COUNT * 2 * 4, "raw/masked output sizes")
    result = []
    for phase in range(2):
        by_key = {}
        for k in range(3):
            for p in range(N):
                for r in range(4):
                    start = ((((phase * 3 + k) * N + p) * 4 + r) * WIDTH) * 4
                    left = struct.unpack_from("<2880I", a, start)
                    right = struct.unpack_from("<2880I", b, start)
                    count = sum(x != y for x, y in zip(left, right, strict=True))
                    if count:
                        need(
                            LEGACY["route"](N, p, r) == 39,
                            "wrong-generation changes outside slot 39",
                        )
                        by_key[f"{k},{p},{r}"] = count
        result.append(by_key)
    return result


def review(root):
    names = ["dense_A", "dense_B", *(f"stage{i}" for i in range(1, 5))]
    weights = [(root / (name + ".f32")).read_bytes() for name in names]
    records = (root / "boundary.tsv").read_text().splitlines()
    need(len(records) == 18, "three MMID/readback observations per graph")
    hist = json.loads((QUAL / "packed_cpu_mixed/receipts/v3-r01-native.json").read_bytes())
    need(
        hashlib.sha256(weights[0]).hexdigest() == hist["scopes"]["3"]["result_sha256"],
        "independent V3 reference A",
    )
    for i, buf in enumerate(weights):
        need(
            len(buf) == COUNT * 8 and buf == weights[i % 2],
            "entire bitwise dense/candidate endpoint",
        )
        for k in range(3):
            size = COUNT * 4 // 3
            start = k * size
            LEGACY["stage_witness"](
                records[3 * i + k],
                LABELS[i],
                N,
                k,
                buf[start : start + size],
                buf[COUNT * 4 + start : COUNT * 4 + start + size],
            )
    diff = changes(weights[0], weights[1])
    for phase in diff:
        need(set(phase) == {"0,0,0", "1,0,0", "2,0,0"}, "all three components distinguish A/B")
    return dict(
        values_per_phase=COUNT,
        output_sha256={
            nm: hashlib.sha256(v).hexdigest() for nm, v in zip(names, weights, strict=True)
        },
        changed_coordinates_by_component_position_rank=diff,
        weight_operand_witnesses=18,
    )
