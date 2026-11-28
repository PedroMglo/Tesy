"""An exact fit for a serial visit can require another frame for next-wave preload."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shadow  # noqa: E402


class LifetimeTests(unittest.TestCase):
    def test_preload_changes_the_minimum_peak(self):
        initial = set(range(1252))
        target = (initial - {0}) | {1252}
        for reverse in (False, True):
            one = shadow.place(initial, target, [{0}, {1252}], reverse)
            two = shadow.place(initial, target, [{0, 1252}, {1252}], reverse)
            self.assertEqual((one["reads"], two["reads"]), (1, 1))
            self.assertEqual((one["peak"], two["peak"]), (1252, 1253))


if __name__ == "__main__":
    unittest.main()
