import copy
import math
import struct
import unittest
from pathlib import Path
from runpy import run_path

m = run_path(Path(__file__).with_name("prepare.py"))
IDS, SLOTS, SHAPES = (m[k] for k in ("IDS", "SLOTS", "SHAPES"))


class TestBridge(unittest.TestCase):
    def test_bit_mutation_and_rank_order(self):
        ff = bytes(11520)
        m["compare_bytes"](ff, ff, "ffn_moe_out")
        with self.assertRaisesRegex(ValueError, "bits"):
            m["compare_bytes"](ff, ff[:-4] + struct.pack("<I", 1), "ffn_moe_out")
        b = {k: bytes(4 * math.prod(sh)) for k, sh in SHAPES.items()}
        b.update(
            ffn_moe_topk=struct.pack("<4i", *IDS), ffn_moe_topk_stream=struct.pack("<4i", *SLOTS)
        )
        m["check_payloads"](b)
        with self.assertRaisesRegex(ValueError, "logical ranks"):
            m["check_payloads"](b | {"ffn_moe_topk": struct.pack("<4i", IDS[1], IDS[0], *IDS[2:])})
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            m["check_payloads"](b | {"ffn_moe_out": struct.pack("<f", math.inf) + ff[4:]})

    def test_single_token_location(self):
        rows = [
            {
                "name": n,
                "file": n + ".bin",
                "phase": "decode0",
                "layer": "0",
                "ne": ",".join(map(str, s)),
                "type": "i32" if "topk" in n else "f32",
                "bytes": str(math.prod(s) * 4),
                "chunk": "-1",
                "state_tokens": "1",
                "first_abs": "189",
            }
            for n, s in SHAPES.items()
        ]
        self.assertEqual(set(m["select_stages"](rows)), set(SHAPES))
        for field, value in (("first_abs", "190"), ("layer", "1"), ("state_tokens", "32")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                m["select_stages"]([rows[0] | {field: value}, *rows[1:]])

    def test_six_consumer_slices(self):
        header = "phase\tlayer\twave\tlogical\tslot\tgeneration\ttensor\tbytes\tstatus\n"
        rows = [
            f"decode0\t0\t0\t{e}\t{s}\t2\t{k}\t{4406400 if k < 3 else 11520}\tEQUAL\n"
            for e, s in zip(IDS, SLOTS, strict=True)
            for k in range(6)
        ]

        def f(rs):
            return m["bindings"]((header + "".join(rs)).encode())

        self.assertEqual(len(f(rows)), 24)
        for bad in (rows[:-1], rows + [rows[0]], [rows[0].replace("EQUAL", "FAILED"), *rows[1:]]):
            with self.assertRaises(ValueError):
                f(bad)

    def test_record_bias_after_padding_and_gate_identity(self):
        stride = 13258752
        index = {
            "align": 4096,
            "alignment": 4096,
            "weight_window": 13221888,
            "stride": stride,
            "pack_bytes": 61096329216,
            "model_sha256_previous_verified": m["schema"]["MODEL"],
            "experts": [None] * 4608,
        }
        for e in IDS:
            comps = []
            for i in range(6):
                n = 11520 if i >= 3 else 4406400
                comps.append(
                    dict(
                        name=f"blk.0.ffn_{m['ROLES'][i % 3]}_exps."
                        + ("bias" if i >= 3 else "weight"),
                        type="f32" if i >= 3 else "mxfp4",
                        size_bytes=n,
                        packed_relative_offset=(13221888 if i >= 3 else 0) + (i % 3) * n,
                        source_offset=e * n,
                        sha256="1" * 64,
                    )
                )
            index["experts"][e] = dict(
                layer=0, tier="CPU", expert=e, pack_offset=e * stride, components=comps
            )
        seen = {(e, 0): 2 for e in IDS}
        p = m["index_rows"](index, seen)
        self.assertEqual(p[0]["components"][3]["pack_absolute_offset"], 28 * stride + 13221888)
        for field, value in (
            ("name", "blk.0.ffn_up_exps.weight"),
            ("sha256", "x"),
            ("packed_relative_offset", 4406400),
        ):
            bad = copy.deepcopy(index)
            bad["experts"][28]["components"][0][field] = value
            with self.assertRaises(ValueError):
                m["index_rows"](bad, seen)


if __name__ == "__main__":
    unittest.main()
