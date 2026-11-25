import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

p = run_path(str(Path(__file__).with_name("score.py")))


class TierScore(unittest.TestCase):
    def test_joint_regions(self):
        # Both clocks need eight; they can only share four.
        r = p["minimum_other"](8, 8, [9, 4, 8])
        self.assertEqual(r["minimum_distinct_other_ns"], 12)
        self.assertEqual(r["minimum_fraction_of_other_union"], 12 / 21)
        r = p["minimum_other"](8, 8, [1, 4, 2])
        self.assertFalse(r["other_regions_suffice"])
        self.assertEqual(
            r["still_required_outside_both_ns"], {"first": 3, "decode": 2, "distinct_at_least": 3}
        )

    def test_distinct_and_causal_boundaries(self):
        calls = [{"number": i, "enter_ns": 10 * i, "return_ns": 10 * i + 9} for i in range(1, 49)]
        spans = [(2, 0, 20, 25), (3, 25, 31, 33), (46, 25, 460, 467), (47, 0, 471, 475)]
        out = p["buckets"](spans, {0: "CPU", 25: "CUDA0"}, calls, 463)
        self.assertEqual(out, {"CPU": [5, 0, 4], "CUDA0": [0, 5, 4]})
        with self.assertRaises(ValueError):
            p["buckets"]([(2, 0, 19, 25)], {0: "CPU"}, calls, 463)

    def test_allocator_proves_no_fallback(self):
        log = "".join(
            f"load_tensors: layer {i} assigned to device {'CPU' if i < 25 else 'CUDA0'},\n"
            for i in range(37)
        )
        log += "alloc_bufs: CPU expert cache size = 12606.81 MiB (40 slots per layer)\n"
        log += "alloc_bufs: CUDA0 expert cache size = 5547.00 MiB (40 slots per layer)\n"
        regs = [
            SimpleNamespace(kind=8, layer=i, component=k, b=4406400)
            for i in range(36)
            for k in range(3)
        ]
        self.assertEqual(p["mapping"](log.encode(), regs)[0][25], "CUDA0")
        for wrong in (
            log.replace("5547.00", "5545.00"),
            log.replace("25 assigned to device CUDA0", "25 assigned to device CPU"),
        ):
            with self.assertRaises(ValueError):
                p["mapping"](wrong.encode(), regs)
