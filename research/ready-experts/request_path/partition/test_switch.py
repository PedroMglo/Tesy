"""Boundary regressions for the marginal first-consumer accounting."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy as p  # noqa: E402
import switch as experiment  # noqa: E402


class VisitTests(unittest.TestCase):
    def test_reloading_an_entry_member_is_the_only_free_job(self):
        visits = [p.Wave(2, 1, 0, 0, (2,)), p.Wave(2, 1, 0, 1, (0,))]
        rows = [[7, 1, 0, 2, 1, [0]], [8, 1, 0, 0, 1, [1]]]
        proof, spare = experiment.per_visit(visits, [0, 1], [0, 2], rows)
        self.assertEqual((proof[0]["floor"], spare), (1, [[8, 0]]))
        with self.assertRaisesRegex(ValueError, "final membership"):
            experiment.per_visit(visits, [0, 1], [1, 2], rows)

    def test_cannot_credit_a_missing_mandatory_read(self):
        visits = [p.Wave(2, 1, 0, -1, (2,))]
        with self.assertRaisesRegex(ValueError, "unserved"):
            experiment.per_visit(visits, [0], [0], [])


if __name__ == "__main__":
    unittest.main()
