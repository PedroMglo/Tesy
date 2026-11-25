import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prefill_interval40.screen import layer_floor, passes  # noqa: E402


class FixedPrefix(unittest.TestCase):
    def test_repeated_demands_pins_and_paid_terminal_set(self):
        g = [(1, 2), (2, 3), (1, 3)]
        self.assertEqual(
            layer_floor(g, {1, 2}, {1, 2}, 2),
            dict(cardinality=1, cardinality_with_F=1, joint=2, joint_with_F=3),
        )
        self.assertEqual(layer_floor(g, set(), {1, 2}, 2)["joint"], 4)

    def test_final_is_optimized_jointly(self):
        g = [(3,), (4,)]
        # Optimization can preserve the valuable entry until the terminal constraint.
        self.assertEqual(layer_floor(g, {1, 2}, {1, 4}, 2)["joint_with_F"], 2)
        self.assertEqual(layer_floor([], {1, 2}, {2, 4}, 2)["joint_with_F"], 1)
        with self.assertRaises(ValueError):
            layer_floor(g, {1, 2}, {1, 2, 3}, 2)

    def test_exact_tenth(self):
        self.assertTrue(passes(90, 100))
        self.assertFalse(passes(91, 101))


if __name__ == "__main__":
    unittest.main()
