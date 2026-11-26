import unittest
from pathlib import Path
from runpy import run_path

mod = run_path(Path(__file__).with_name("screen.py"))


class CutTests(unittest.TestCase):
    def test_cut(self):
        seq = [b"text before", *mod["INTRO"], b"ab", b"c", b""]
        self.assertEqual(mod["text_cut"](seq, [b"ab", b"c"]), 7)
        self.assertIsNone(mod["text_cut"](seq, [b"a", b"bc"]))
        self.assertIsNone(mod["text_cut"]([*mod["INTRO"], *seq], [b"ab", b"c"]))

    def test_no_credit_past_first_delta(self):
        labels = 23 * ["ar"] + 11 * ["anchor"] + 12 * ["skip"]
        ticks = list(range(47))
        r = mod["budget"](labels, ticks, 24, 11_000_000_000, 46_000)
        self.assertEqual(r["eligible_before_ns"], 1000)
        self.assertEqual(r["eligible_after_ns"], 22_000)
        self.assertEqual(r["first_final_if_all_eligible_free_ns"], 10_999_999_000)
        self.assertEqual(r["before_counts"]["anchor"], 1)
        self.assertLess(r["total_verification_and_overhead_available_ns"], 0)
        self.assertNotIn("eligible_before_ns", mod["budget"](labels, ticks, None, 0, 46_000))

    def test_invalid_counts_or_clocks(self):
        with self.assertRaises(ValueError):
            mod["budget"](["ar"], [0, 1], 1, 0, 0)
        with self.assertRaises(ValueError):
            mod["budget"](["ar"], [3, 1], 1, 0, 0)


if __name__ == "__main__":
    unittest.main()
