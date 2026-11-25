import itertools
import tempfile
import unittest
from collections import Counter, namedtuple
from pathlib import Path
from runpy import run_path

E = run_path(str(Path(__file__).with_name("evaluate.py")))
COST = E["B"]["cost"]


class RetentionEvaluation(unittest.TestCase):
    def test_global_capacity_and_partial_credit(self):
        # Identical counts admit different choices when one site has a larger overlap.
        for whole in (False, True):
            for gaps in itertools.product((0, 7, 20), repeat=3):
                sites = [(i, 2 + (i % 2), 2, gap) for i, gap in enumerate(gaps)]
                for cap in (0, 1, 3, 5, 20):
                    chosen = E["best_counts"](sites, 10, whole, cap)
                    self.assertLessEqual(sum(chosen.values()), cap)
                    costs = []
                    for ks in itertools.product(range(3), repeat=3):
                        if sum(ks) <= cap:
                            costs.append(
                                sum(
                                    COST(n - k, g, 10, whole)
                                    for (_, n, _, g), k in zip(sites, ks, strict=True)
                                )
                            )
                    self.assertEqual(
                        sum(COST(n - chosen[i], g, 10, whole) for i, n, _, g in sites), min(costs)
                    )

    def test_banks_with_same_cardinality_can_have_different_margins(self):
        site1, site2 = (1, 1, 0, -1), (2, 2, 5, 0)
        k1, k2 = (0, 19), (5, 19)
        x, table = E["project"](
            {k1: site1, k2: site2},
            {site1: 0, site2: 10_000_000},
            {"prefill": {k1}, "lru": {k2}},
            {k1, k2},
            0,
            capacity=1,
        )
        y = x["8000000000_partial"]
        self.assertEqual(y["prefill"]["conditional_floor_ns"], 0)
        self.assertEqual(y["retrospective"]["served_keys"], 1)
        self.assertEqual(y["lru"]["conditional_floor_ns"], E["SIZE"] // 8)
        self.assertEqual([s["prefill"] + s["lru"] for s in table], [1, 1])
        self.assertEqual(E["delta"]({k1: site1}, {k1: site2})["different"], 1)

    def test_frozen_prefix_is_immutable_and_later_reservations_count_separately(self):
        r = namedtuple("Row", "kind call layer expert")
        rows = [r(11, 1, 0, 7), r(17, 1, 0, 7), r(11, 2, 25, 0), r(11, 3, 25, 0), r(11, 4, 25, 12)]
        got, used = E["delivery"](rows, {(0, 7), (25, 0)}, {0: "CPU", 25: "CUDA0"})
        self.assertEqual(used, {"CPU": 1, "CUDA0": 1})
        for phase, tier in [("prefill", "CPU"), ("prefill", "CUDA0"), ("decode", "CUDA0")]:
            self.assertEqual(got[phase][tier], {"reservations": 1, "payload_bytes": E["SIZE"]})
        self.assertEqual(got["decode"]["CPU"]["reservations"], 0)

    def test_changed_digests_or_site_domain_fail(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "family.json"
            path.write_text("{}")
            with self.assertRaises(ValueError):
                E["read_new"](path.parent, "0" * 64)
        with self.assertRaises(ValueError):
            E["project"]({}, {1: 10}, {}, set(), 0)
        self.assertEqual(E["best_counts"]([(0, 2, 2, 80)], 10, False, 2), Counter())


if __name__ == "__main__":
    unittest.main()
