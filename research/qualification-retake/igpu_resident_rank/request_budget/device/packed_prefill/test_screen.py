import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen


class Budget(unittest.TestCase):
    def test_rate_denom_and_credit(self):
        N = screen.NS

        def scenario(r, k, at):
            return screen.budget(
                18 * N, 10 * N, 9 * N, r, k, 8 * N, Fraction(at), (16 * N, 17 * N), (14 * N, 15 * N)
            )

        six = scenario(6, 47, 1)
        zero = scenario(10, 47, 0)
        half = scenario(10, 47, Fraction(1, 2))
        ten = scenario(10, 47, 1)
        self.assertAlmostEqual(six["native_decode_budget_ns_floor"] / N, 47 / 6)
        self.assertEqual(zero["prefill_available_ns_floor"], 2 * N)
        self.assertEqual(
            half["prefill_available_ns_floor"], (ten["prefill_available_ns_floor"] + 2 * N) // 2
        )
        self.assertNotEqual(
            six["prefill_available_ns_floor"], scenario(6, 46, 1)["prefill_available_ns_floor"]
        )
        self.assertEqual(ten["decode"]["lower_bytes"], 14 * N)
        self.assertEqual(ten["prefill"]["lower_bytes"], 16 * N)

    def test_decision_at_boundary(self):
        self.assertEqual(screen.decision(5.99, 1, 2, 2), "INSUFFICIENT_DECODE_IN_THIS_SCENARIO")
        self.assertEqual(screen.decision(6, 4), "UNIDENTIFIED_EXPOSED_SERVICE")
        self.assertEqual(screen.decision(6, 4, 3), "EXCLUDE_SCHEDULE_ONLY_IN_THIS_SCENARIO")
        self.assertEqual(screen.decision(8, 4, 5, 3), "NO_WITNESS_AT_REQUIRED_GAIN")
        self.assertEqual(screen.decision(6, 4, 4, 4), "ADMIT_CONTROLLED_TEST_ONLY")
        with self.assertRaises(ValueError):
            screen.decision(6, 4, 2, 4)


if __name__ == "__main__":
    unittest.main()
