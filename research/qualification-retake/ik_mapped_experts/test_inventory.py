"""Negative controls for the metadata that determines original-file page identity."""

import json
import unittest
from pathlib import Path
from runpy import run_path

verify = run_path(str(Path(__file__).with_name("verify.py")))


def inventory():
    base = 13_022_240
    cursor = base
    header = {"gguf_version": 3, "alignment": 32, "data_offset": base, "tensor_count": 687}
    rows = []
    for layer in range(36):
        for role in verify["ROLES"]:
            for kind, shape, dtype, size in (
                ("weight", [2880, 2880, 128], "mxfp4", 128 * verify["STRIDE"]),
                ("bias", [2880, 128], "f32", 128 * 2880 * 4),
            ):
                rows.append(
                    dict(
                        name=f"blk.{layer}.ffn_{role}_exps.{kind}",
                        shape=shape,
                        tensor_type=dtype,
                        n_bytes=size,
                        data_offset=cursor,
                        relative_data_offset=cursor - base,
                    )
                )
                cursor += size
    rows.extend(dict(name=f"other.{i}") for i in range(687 - len(rows)))
    return [header, *rows]


def parse(rows):
    return verify["layer_geometry"]("\n".join(map(json.dumps, rows)).encode())


class Metadata(unittest.TestCase):
    def test_two_weights_cannot_claim_the_same_file_interval(self):
        rows = inventory()
        self.assertEqual(len(parse(rows)), 36)
        for k in ("data_offset", "relative_data_offset"):
            rows[3][k] = rows[1][k]
        with self.assertRaisesRegex(ValueError, "aliased"):
            parse(rows)

    def test_packed_bias_shape_cannot_stand_in_for_separate_bias(self):
        rows = inventory()
        rows[2]["shape"] = [5760, 64]
        with self.assertRaisesRegex(ValueError, "dimensions"):
            parse(rows)
