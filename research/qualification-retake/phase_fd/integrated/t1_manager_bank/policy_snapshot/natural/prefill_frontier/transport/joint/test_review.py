import unittest
from pathlib import Path
from runpy import run_path

review = run_path(Path(__file__).with_name("review.py"))


class ServiceReviewTests(unittest.TestCase):
    def test_touching_intervals_and_cross_worker_overlap(self):
        self.assertEqual(review["occupancy"]([(1, 3), (3, 5), (2, 5)], 7), [3, 1, 3, 0, 0])
        with self.assertRaisesRegex(ValueError, "outside"):
            review["occupancy"]([(2, 8)], 7)
        with self.assertRaisesRegex(ValueError, "concurrency"):
            review["occupancy"]([(0, 5)] * 5, 5)

    def test_reread_uses_same_order_and_all_component_digests(self):
        group = dict(tier="CPU", layer=0, wave=1, tile=3)
        job = dict(
            ordinal=2,
            expert=10,
            slot=3,
            generation=4,
            source_enqueue=2,
            components=[{"sha256": s} for s in ("gate", "down", "up")],
        )
        row = {**group, **job, "index": 0, "component_sha256": ["gate", "down", "up"]}
        review["inspect_integrity"]({"jobs": [row]}, [(group, job)])
        for change in ({"generation": 3}, {"component_sha256": ["up", "down", "gate"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                review["inspect_integrity"]({"jobs": [row | change]}, [(group, job)])


if __name__ == "__main__":
    unittest.main()
