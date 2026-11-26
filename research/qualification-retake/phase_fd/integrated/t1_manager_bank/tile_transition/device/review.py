"""All coordinates, placements and the closed C291 transport must agree in each child."""

import hashlib
import math
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
cpu = run_path(str(HERE.parent / "review.py"))
need = cpu["require"]


def vector(directory, name):
    raw = (directory / (name + ".f32")).read_bytes()
    need(len(raw) == 2880 * 4, "wrong FFN width")
    floats = struct.unpack("<2880f", raw)
    need(all(map(math.isfinite, floats)) and any(floats), "empty or nonfinite FFN")
    return raw


def check_child(arm, case_dir, reference_dir, row, gold):
    need(row["status"] == "PASS_C291_TILE_TRANSITION_CUDA" and row["arm"] == arm, "CUDA status")
    transport = cpu["case"](arm, row | {"status": "PASS_C291_TILE_TRANSITION_CPU"}, gold)
    names = {"reader", "decode"} | ({"old-gold", "new-gold"} if arm == "reference" else set())
    need(set(row["operator_rows"]) == names, "operator coverage")
    old, new = [vector(reference_dir, key) for key in ("old-gold", "new-gold")]
    need(old != new, "negative must discriminate generations")
    values = {name: vector(case_dir, name) for name in names}
    need(values["reader"] == (new if arm == "broken" else old), "full FFN reader")
    need(values["decode"] == vector(reference_dir, "decode"), "full FFN first decode")
    all_ids = {
        "reader": [0, 1, 6, 4],
        "old-gold": [0, 1, 6, 4],
        "new-gold": [3, 5, 0, 2],
        "decode": [6, 7, 2, 4],
    }
    for name, raw in values.items():
        op = row["operator_rows"][name]
        need(
            op
            == {
                "floats": 2880,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "ids": all_ids[name],
                "mask": [1] * 4 if name == "decode" else [0, 0, 1, 1],
                "mmid": 3,
                "original_operands": 3,
                "device": "CUDA0",
                "view": name == "reader" and arm in ("reference", "bank"),
                "event": name == "reader" and arm == "disk",
            },
            "operator/device/observable edge",
        )
    return {
        "transport": transport,
        "output_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(values.items())},
        "differing_gold_coordinates": sum(
            x != y
            for x, y in zip(
                struct.iter_unpack("<I", old), struct.iter_unpack("<I", new), strict=True
            )
        ),
    }
