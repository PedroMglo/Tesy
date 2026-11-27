import itertools
import struct
import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

M = run_path(str(Path(__file__).with_name("screen.py")))
Call = M["Call"]


class ReadyBounds(unittest.TestCase):
    def test_four_workers_and_layer_barrier(self):
        self.assertEqual(M["layer_fourths"]([8, 1, 1, 1]), 32)
        self.assertEqual(M["layer_fourths"]([2] * 5), 10)
        group = (1, 1, 0)
        waves = [
            SimpleNamespace(
                site=(*group, 0), start=1, end=9, reserved={1, 2}, required_service={1: 7, 2: 6}
            ),
            SimpleNamespace(
                site=(1, 1, 1, 0), start=11, end=16, reserved={3}, required_service={3: 4}
            ),
        ]
        calls = [{"number": 1, "enter_ns": 0, "return_ns": 20}]
        (c,) = M["partition"](calls, waves)
        self.assertEqual((c.span, c.remap, c.service_fourths), (20, 13, 44))
        self.assertEqual(c.measures(1_000_000)["ready"], 11)
        waves[1].start = 8
        with self.assertRaisesRegex(ValueError, "overlapping"):
            M["partition"](calls, waves)

    def test_distinct_clocks_and_serial_calls(self):
        calls = [
            Call(1, 20, 12, 32, 2, 1),
            Call(2, 10, 0, 0, 0, 0),
            Call(3, 6, 3, 8, 1, 1),
            Call(47, 10, 7, 20, 1, 1),
        ]
        r, _, exterior = M["clocks"](calls, 37, 18)
        self.assertEqual(exterior, {"first_final": 1, "decode": 2})
        self.assertEqual(
            (r["fixed_callbacks"]["first_final"], r["fixed_callbacks"]["decode"]), (26, 12)
        )
        self.assertEqual((r["ready"]["first_final"], r["ready"]["decode"]), (22, 10))
        with self.assertRaisesRegex(ValueError, "exceed"):
            M["clocks"](calls, 35, 18)

    def test_service_price_and_both_deadlines(self):
        self.assertEqual(M["frontier"](lambda p: p <= 583_431)["max_ppm"], 583_431)
        self.assertIsNone(M["frontier"](lambda _: False)["max_ppm"])
        self.assertEqual(M["frontier"](lambda _: True)["max_ppm_tested"], 1_000_000)
        self.assertLess(M["joint"]({"first_final": 1, "decode": 7_833_333_334}), 0)
        self.assertEqual(M["joint"]({"first_final": 1, "decode": 7_833_333_333}), 0)
        self.assertEqual(M["consensus"]([True, False]), "INCONCLUSIVE_BETWEEN_RUNS")

    def test_completion_order_is_observable_in_float32(self):
        # A small independent arithmetic witness. Real GGML uses its own frozen tree.
        def ordered_sum(xs):
            acc = 0.0
            for x in xs:
                acc = struct.unpack("<f", struct.pack("<f", acc + x))[0]
            return struct.pack("<f", acc)

        reference = [struct.unpack("<f", struct.pack("<f", x))[0] for x in (1e20, -1e20, 3, 4)]
        expected = ordered_sum(reference)
        wrong = 0
        for order in itertools.permutations(range(4)):
            private = [None] * 4
            for rank in order:
                private[rank] = reference[rank]
            self.assertEqual(ordered_sum(private), expected)
            wrong += ordered_sum(reference[k] for k in order) != expected
        self.assertGreater(wrong, 0)


if __name__ == "__main__":
    unittest.main()
