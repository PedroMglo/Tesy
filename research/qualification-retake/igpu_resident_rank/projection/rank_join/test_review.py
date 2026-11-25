import operator
import struct
import sys
import unittest
from pathlib import Path
from runpy import run_path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review


def f(*x):
    return struct.pack("<" + str(len(x)) + "f", *x)


class RankComposition(unittest.TestCase):
    def test_bias_and_router_rank_identity(self):
        down = f(1.5, -2)
        right_bias, wrong_bias = f(0.5, 3), f(3, 0.5)
        mix = f(0.5, 0.25, 0.125, 0.125)
        others = f(0, 0, 1, 1, 2, 2, 3, 3)
        biased, weighted, result = review.join_down(down, right_bias, mix, others)
        self.assertEqual((biased, weighted, result), (f(2, 1), f(1, 0.5), f(7, 6.5)))
        for b, m in [(wrong_bias, mix), (right_bias, f(0.25, 0.5, 0.125, 0.125))]:
            self.assertEqual(
                review.compare(review.join_down(down, b, m, others)[2], result)["different"], 2
            )

    def test_left_association_and_zero_bits(self):
        _, _, value = review.join_down(f(2**27), f(0), f(1, 1, 1, 1), f(0, -(2**27), 1, 2))
        right = review.apply(f(2**27), review.apply(f(-(2**27)), f(3), operator.add), operator.add)
        self.assertEqual(value, f(3))
        self.assertNotEqual(value, right)
        self.assertEqual(review.compare(f(-0.0), f(0.0))["different"], 1)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            review.compare(f(float("nan")), f(0))

    def test_distinct_rhs_code_and_scale(self):
        a = run_path(
            str(Path(review.__file__).resolve().parent.parent / "rank_activation/grade.py")
        )
        base = bytes(3060)
        for pos, key in [(0, "changed_scales"), (34 * 89 + 33, "changed_codes")]:
            changed = bytearray(base)
            changed[pos] = 1
            d = a["q_diff"](base, changed)
            self.assertFalse(d["same_input"])
            self.assertEqual(d[key], 1)

    def test_record_extent_logical_and_role(self):
        row = {
            "expert": 28,
            "layer": 0,
            "tier": "CPU",
            "pack_offset": 371245056,
            "components": [{}, {}, {}],
        }
        for i, role in enumerate(("gate", "down", "up")):
            row["components"].append(
                dict(
                    type="f32",
                    name=f"blk.0.ffn_{role}_exps.bias",
                    size_bytes=11520,
                    packed_relative_offset=13221888 + 11520 * i,
                    sha256="a" * 64,
                )
            )
        ex = [None] * 4608
        ex[28] = row
        idx = dict(
            alignment=4096,
            weight_window=13221888,
            stride=13258752,
            pack_bytes=61096329216,
            experts=ex,
        )
        d = review.bias_descriptors(idx)
        self.assertEqual(d["gate"]["offset"], 384466944)
        self.assertEqual(sum(v["bytes"] for v in d.values()), 34560)
        row["components"][3], row["components"][5] = row["components"][5], row["components"][3]
        with self.assertRaisesRegex(ValueError, "role"):
            review.bias_descriptors(idx)


if __name__ == "__main__":
    unittest.main()
