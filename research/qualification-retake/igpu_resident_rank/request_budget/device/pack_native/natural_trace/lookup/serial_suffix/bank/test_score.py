import unittest
from pathlib import Path
from runpy import run_path

F = run_path(str(Path(__file__).with_name("score.py")))
Wave = F["BANK"]["Wave"]


def wave(il, start, duration, drained=False, hit=False, residual=0):
    w = Wave((3, 0, il, 0), start, drained, start + duration, False)
    w.reserved = {(il, 0, 1, 10)} if hit else set()
    w.required_service = {(il, 1, 1, 11): residual} if residual else {}
    return w


class TestCombined(unittest.TestCase):
    def test_removed_hit_and_drain(self):
        waves = [
            wave(24, 10, 100, hit=True),
            wave(25, 110, 45, residual=13),
            wave(26, 155, 12, drained=True),
            wave(27, 167, 18, hit=True, residual=6),
        ]
        _, modes, _ = F["census"](waves, ["prefill", "prefill", "anchor"], {(24, 10), (27, 10)})
        for mode, expected, floor in (
            ("direct", 18, 6),
            ("drained_retained_origins", 18, 6),
            ("drained", 63, 19),
            ("persistent", 75, 19),
        ):
            c = modes[mode]["decode_first"]
            self.assertEqual(c["retained_covered_ns"], expected)
            self.assertEqual(c["retained_floor_1x_ns"], floor)
        self.assertEqual(modes["persistent"]["decode_first"]["overlap_already_free_ns"], 100)
        self.assertEqual(modes["drained"]["decode_first"]["retained_floor_half_ns"], 9)

    def test_empty_and_rotation(self):
        w = [wave(0, 0, 12, hit=True), wave(29, 12, 8)]
        _, m, _ = F["census"](w, ["prefill", "prefill", "ar"], set())
        self.assertEqual(m["persistent"]["decode_first"]["retained_covered_ns"], 0)
        _, m, _ = F["census"](w, ["prefill", "prefill", "ar"], {(0, 10)})
        self.assertEqual(m["persistent"]["decode_first"]["retained_covered_ns"], 20)

    def test_distinct_clocks(self):
        from collections import Counter

        phases = {
            p: Counter(retained_covered_ns=ns)
            for p, ns in (("prefill", 30), ("decode_first", 16), ("decode_tail", 8))
        }
        suffix = {
            k: {"target_ns": t, "attempts": n, "fractions": {"0": {"projected_ns": 60}}}
            for k, t, n in (("first", 30, 2), ("decode", 35, 3))
        }
        o = F["price"](suffix, 44, phases)["free"]
        self.assertEqual((o["prefill_ns"], o["first_final_ns"], o["decode_ns"]), (14, 14, 36))
        self.assertEqual(o["joint"], "NO_GO_FIXED_SCENARIO")
        self.assertEqual(o["uniform_extra_per_attempt_ns"], -1)


if __name__ == "__main__":
    unittest.main()
