import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan import EXPERT_BYTES, Pool, compare, project_i, simulate, totals, waves  # noqa: E402


class RouteGeometry(unittest.TestCase):
    def test_width_and_first_touch_define_geometry(self):
        # The switch is based on potential touches, even when only four experts occur.
        repeated = [(9, 2, 8, 1)] * 10
        self.assertEqual(waves(repeated), [[9, 2, 8, 1] * 10])
        self.assertEqual(waves(repeated + repeated[:1]), [[9, 2, 8, 1] * 11, [], []])
        # 44 distinct demands in 3 slices, nonmonotonic expert order and repeated votes.
        rows = [tuple(range(44 - 4 * i, 40 - 4 * i, -1)) for i in range(11)]
        rows.append((43, 26, 25, 1))
        groups = waves(rows)
        self.assertEqual(groups[0], list(range(44, 26, -1)) + [43])
        self.assertEqual(groups[1], list(range(26, 8, -1)) + [26, 25])
        self.assertEqual(groups[2], list(range(8, 0, -1)) + [1])
        with self.assertRaises(ValueError):
            waves([(3, 1, 2, 3)])


class Placement(unittest.TestCase):
    def test_prior_votes_carry_evicted_experts_and_preserve_pins(self):
        policies = [Pool(name, 4) for name in ("votes", "lru")]
        for pool in policies:
            pool.serve([1, 1, 1, 1, 2, 3, 4])
            counter = pool.serve([5, 4])
            self.assertEqual((counter["misses"], counter["hits"], counter["evictions"]), (1, 1, 1))
            self.assertIn(4, pool.resident)
        self.assertEqual(policies[0].resident, {1, 3, 4, 5})
        self.assertEqual(policies[1].resident, {2, 3, 4, 5})
        for pool in policies:
            pool.serve([1, 1])
            self.assertEqual(pool.votes[1], 6)
            before = (set(pool.resident), pool.clock, pool.votes.copy())
            self.assertEqual(pool.serve([])["parking_only_waves"], 1)
            self.assertEqual(before, (pool.resident, pool.clock, pool.votes))
            with self.assertRaises(ValueError):
                pool.serve([1, 2, 3, 4, 5])

    def test_victim_uses_previous_wave_recency_then_id(self):
        p = Pool("votes", 2)
        p.serve([8, 2])
        p.serve([1])
        self.assertEqual(p.resident, {1, 2})
        p.last[2] = p.last[1]  # Explicitly exercise the stable ID fallback.
        p.serve([4])
        self.assertEqual(p.resident, {2, 4})

    def test_changing_future_preserves_prefix_state_and_cost(self):
        prefix = [(1, 1, 0, i, tuple((4 * i + j) % 100 for j in range(4))) for i in range(32)]
        target = [set() for _ in range(36)]

        def run(ids):
            return simulate(prefix + [(9, 1, 0, 32, ids)], "votes", target)

        one, two = run((0, 1, 2, 3)), run((93, 94, 95, 96))
        self.assertEqual(one["phases"]["prefix"], two["phases"]["prefix"])
        self.assertEqual(one["P_membership_sha256"], two["P_membership_sha256"])
        self.assertNotEqual(one["I_membership_sha256"], two["I_membership_sha256"])

    def test_no_reset_between_calls_and_tier_charge(self):
        rows = [
            (8, 1, 0, 10, (1, 2, 3, 4)),
            (8, 1, 25, 10, (9, 8, 7, 6)),
            (9, 1, 0, 11, (4, 3, 5, 1)),
            (9, 1, 25, 11, (9, 8, 7, 6)),
        ]
        target = [set() for _ in range(36)]
        target[0] = {1, 2, 3, 10}
        out = simulate(rows, "lru", target)
        self.assertEqual(totals(out), {"prefix": 8, "increment": 1, "restored_total": 10})
        self.assertEqual(out["phases"]["increment"]["CPU"]["hits"], 3)
        self.assertEqual(out["phases"]["increment"]["CUDA0"]["logical_load_bytes"], 0)
        self.assertEqual(out["restore_I_identity_floor"]["CPU"]["logical_load_bytes"], EXPERT_BYTES)
        self.assertEqual(out["restore_I_identity_floor"]["CPU"]["excess_identities"], 2)

    def test_zero_repair_and_invalid_capacity(self):
        caches = [Pool("lru", 4) for _ in range(36)]
        caches[25].serve([3, 2, 1, 0])
        target = [set(p.resident) for p in caches]
        self.assertEqual(project_i(caches, target)["CUDA0"]["loads"], 0)
        target[25].add(33)
        with self.assertRaises(ValueError):
            project_i(caches, target)

    def test_exact_threshold_and_restoration_cost(self):
        control = {"prefix": 200, "increment": 100, "restored_total": 315}
        candidate = {"prefix": 200, "increment": 90, "restored_total": 315}
        self.assertTrue(compare(candidate, control)["pass"])
        for field in candidate:
            changed = dict(candidate)
            changed[field] += 1
            self.assertFalse(compare(changed, control)["pass"])


if __name__ == "__main__":
    unittest.main()
