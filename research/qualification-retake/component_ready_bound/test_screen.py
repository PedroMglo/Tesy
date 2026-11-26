import unittest

from screen import CHAIN, Inconclusive, certificate, summarize, threshold


def generation(slot, base):
    return ((slot, 1), {phase: base + 3 * i for i, phase in enumerate(CHAIN)})


class FloorTests(unittest.TestCase):
    def setUp(self):
        self.ranks = [(e, 0, -1, 0) for e in range(2)] + [(e, 2, e, 3) for e in (2, 3)]
        self.jobs = {e: generation(e, 100 + e) for e in (0, 1)}

    def test_overlapping_ranks_and_hits(self):
        self.assertEqual(certificate(self.ranks, self.jobs, 99, 150), (6, 2))
        self.assertEqual(certificate([(e, 2, e, 1) for e in range(4)], {}, 2, 2), (0, 0))

    def test_boundary_identity_and_missing(self):
        with self.assertRaises(Inconclusive):
            certificate(self.ranks, self.jobs, 99, 140)
        with self.assertRaises(Inconclusive):
            certificate(self.ranks, dict(self.jobs, extra=generation(3, 100)), 99, 150)
        with self.assertRaises(Inconclusive):
            certificate(self.ranks, {0: self.jobs[0]}, 99, 150)
        with self.assertRaises(Inconclusive):
            certificate([self.ranks[0], (1, 1, 4, 3), *self.ranks[2:]], self.jobs, 99, 150)
        with self.assertRaises(Inconclusive):
            summarize(
                iter(
                    [
                        "kind us call route layer expert slot gen component bytes rows",
                        "2 0 1 2 0 -1 -1 0 -1 0 1",
                        "6 1 1 3 0 1 7 1 0 4406400 0",
                    ]
                ),
                "nominal153",
            )

    def test_sequential_components(self):
        del self.jobs[0][1][1, 6]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            certificate(self.ranks, self.jobs, 99, 150)
        self.jobs[0] = generation(0, 100)
        self.jobs[0][1][1, 6] = 100
        with self.assertRaises(Inconclusive):
            certificate(self.ranks, self.jobs, 99, 150)

    def test_strict_threshold(self):
        self.assertFalse(threshold(5_333_333, 1, 1)["exceeds_six_step_budget"])
        self.assertTrue(threshold(5_333_334, 1, 1)["exceeds_six_step_budget"])
        self.assertFalse(threshold(6_666_666, 4, 5)["exceeds_six_step_budget"])
        self.assertTrue(threshold(6_666_667, 4, 5)["exceeds_six_step_budget"])
