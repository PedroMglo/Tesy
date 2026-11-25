"""Verify the contemporary physical slot order at the end of the 153-token increment."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HISTORICAL = HERE.parent / "cache_boundary_evidence/receipt.json"
HISTORICAL_SHA = "efabd76727b58ad3ceaca4a79b535afd49f31d2be6aadc2243b0675cf60bd20f"


def verify(case, path):
    if (
        case not in {"nominal153", "code153"}
        or hashlib.sha256(HISTORICAL.read_bytes()).hexdigest() != HISTORICAL_SHA
    ):
        raise ValueError("case or independent C294 receipt")
    if not 0 < path.stat().st_size < 2**20:
        raise ValueError("boundary dump size")
    data = json.loads(path.read_bytes())
    if (
        data["schema"] != "routed-cache-boundary-i-v1"
        or type(data["pending_queue"]) is not int
        or data["pending_queue"] != 0
    ):
        raise ValueError("boundary schema or queued work")
    layers = data["slot_vector"]
    if len(layers) != 36 or any(len(layer) != 40 for layer in layers):
        raise ValueError("boundary shape")
    occupied = 0
    for layer in layers:
        residents = set()
        for group in layer:
            if len(group) != 4 or any(type(v) is not int for v in group):
                raise ValueError("physical slot record")
            expert, generation, state, claimed = group
            if not (
                generation >= 0
                and claimed == 0
                and (
                    (expert == -1 and state == 0)
                    or (state == 2 and 0 <= expert < 128 and expert not in residents)
                )
            ):
                raise ValueError("unexpected slot state")
            if state == 2:
                residents.add(expert)
        occupied += len(residents)
    h = hashlib.sha256(json.dumps(layers, separators=(",", ":")).encode()).hexdigest()
    arms = json.loads(HISTORICAL.read_bytes())["arms"]
    if any(arms[f"c294-{case}-{n}-on"]["boundary_slot_vector_sha256"] != h for n in (2, 3)):
        raise ValueError("historical or contemporary physical slot vector differs")
    if occupied != 1411 or type(data["copy_ns"]) is not int or data["copy_ns"] <= 0:
        raise ValueError("boundary occupancy or copy clock")
    return {
        "slot_vector_sha256": h,
        "copy_ns": data["copy_ns"],
        "resident_slots": occupied,
        "empty_slots": 1440 - occupied,
        "reserved_object_bytes": data["reserved_object_bytes"],
    }
