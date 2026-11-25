import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("screen.py")))


class TestComposition(unittest.TestCase):
    def test_disjoint_credit(self):
        calls = [dict(number=i + 1, enter_ns=100 * i + 1, return_ns=100 * i + 81) for i in range(4)]
        spans = [(1, 5, 20), (1, 21, 26), (2, 101, 181), (3, 202, 272), (4, 321, 331)]
        r = M["savings"](calls, spans, ["prefill", "anchor", "skip", "ar"])
        first = M["price"](r[:3], 300, 110, False)
        self.assertEqual(first["eligible_retained_remap_ns"], 20)
        self.assertEqual(first["fractions"]["100"]["projected_ns"], 120)
        free = M["price"](r[:3], 300, 110, True)
        self.assertEqual(free["fractions"]["100"]["projected_ns"], 60)
        decode = M["price"](r[1:], 300, 190, False)
        t = M["together"](first, decode)
        self.assertEqual(t["joint_required_fraction_at_free_verification"], 1.5)
        self.assertEqual(t["both_targets"]["100"]["status"], "NO_GO_FIXED_PRICES")
        self.assertEqual(decode["eligible_retained_remap_ns"], 10)

    def test_overlap_and_escape(self):
        call = [dict(number=1, enter_ns=10, return_ns=20)]
        for bad in ([(1, 9, 12)], [(1, 11, 15), (1, 14, 17)], [(2, 11, 12)]):
            with self.assertRaises(ValueError):
                M["savings"](call, bad, ["ar"])

    def test_no_remap_and_zero_cost(self):
        r = [("ar", 5, 0), ("anchor", 0, 0)]
        self.assertIsNone(M["price"](r, 9, 1, True)["required_fraction"])
        self.assertEqual(M["price"](r, 9, 5, True)["fractions"]["50"]["projected_ns"], 5)
        with self.assertRaises(ValueError):
            M["price"](r, 2, 1, False)


if __name__ == "__main__":
    unittest.main()
