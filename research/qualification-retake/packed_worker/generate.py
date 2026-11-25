"""Create six synthetic C290-shaped entries. No source weights or model access."""

import argparse
import hashlib
import json
import os
from pathlib import Path

SLAB = 4_406_400
WINDOW = 13_221_888
STRIDE = 13_258_752
SLOTS = 40


def generate(out):
    out.mkdir(mode=0o700)
    whole = hashlib.sha256()
    records = []
    scale_codes = bytes(122 + i % 8 for i in range(256))
    with (out / "experts.pack").open("xb") as f:
        for rec in range(6):
            checks = []
            for role in ("gate", "down", "up"):
                if rec:
                    seed = f"C291-fixture-v1/record{rec}/{role}".encode()
                    data = bytearray(hashlib.shake_256(seed).digest(SLAB))
                    data[::17] = data[::17].translate(scale_codes)
                else:
                    data = bytearray(SLAB)
                f.write(data)
                whole.update(data)
                checks.append(hashlib.sha256(data).hexdigest())
            padding = bytes([0xA1 + rec]) * (WINDOW - 3 * SLAB)
            biases_and_gap = bytes(STRIDE - WINDOW)
            for section in (padding, biases_and_gap):
                f.write(section)
                whole.update(section)
            records.append(
                {
                    "record": rec,
                    "offset": rec * STRIDE,
                    "role_sha256": checks,
                    "weight_window_tail_sha256": hashlib.sha256(padding).hexdigest(),
                }
            )
        f.flush()
        os.fsync(f.fileno())
    pack = out / "experts.pack"
    if pack.stat().st_size != 6 * STRIDE or pack.stat().st_size >= 192 * 2**20:
        raise ValueError("unexpected geometry")
    gold = {
        "schema": "synthetic-c291-slot-v1",
        "expert_count": 128,
        "slots": SLOTS,
        "pack_bytes": pack.stat().st_size,
        "pack_sha256": whole.hexdigest(),
        "slab": SLAB,
        "pack_stride": STRIDE,
        "window": WINDOW,
        "roles": ["gate", "down", "up"],
        "records": records,
        "expert_records": [0] * 36 + [1, 2, 3, 4, 5],
        "unused_experts": "unmapped: service must reject",
    }
    with (out / "gold.json").open("x") as f:
        json.dump(gold, f, indent=2, sort_keys=True)
        f.write("\n")
    pack.chmod(0o444)
    (out / "gold.json").chmod(0o444)
    print("SYNTHETIC_PACK_CREATED", 6 * STRIDE, whole.hexdigest())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-output-dir", type=Path, required=True)
    generate(p.parse_args().new_output_dir)
