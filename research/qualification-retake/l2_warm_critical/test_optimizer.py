import sys
import unittest
from itertools import combinations, product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from l2_warm_critical.optimizer import resolve  # noqa: E402


def brute(groups, k):
    keys = sorted(key for group in groups for key, _, _, s in group if s == "eligible")
    variants = []
    for n in range(min(k, len(keys)) + 1):
        for picks in combinations(keys, n):
            total = sum(
                max(
                    (c if key in picks or s == "free" else r + c for key, r, c, s in group),
                    default=0,
                )
                for group in groups
            )
            variants.append((total, n, picks))
    return min(variants)


class InitialCopies(unittest.TestCase):
    def test_complementarity_and_no_unnecessary_copies(self):
        a, b, c = (1, 0), (1, 1), (2, 0)
        groups = [[(a, 9, 1, "eligible"), (b, 9, 1, "eligible")], [(c, 3, 0, "eligible")], []]
        result = resolve(groups, [1, 2, 3, 20])
        self.assertEqual(result[0], dict(gain_us=0, group_max_sum_us=13, chosen=[]))
        self.assertEqual(result[1]["chosen"], [c])
        self.assertEqual(result[2], dict(gain_us=9, group_max_sum_us=4, chosen=[a, b]))
        self.assertEqual(result[3], result[20])
        groups.append([(a, 9, 10, "free")])
        self.assertEqual(resolve(groups, [2])[2]["group_max_sum_us"], 14)

    def test_tie_prefers_fewer_then_lexicographic_keys(self):
        a, b, c = (1, 2), (1, 1), (3, 0)
        groups = [[(a, 8, 0, "eligible"), (b, 8, 0, "eligible")], [(c, 8, 0, "eligible")]]
        self.assertEqual(resolve(groups, [2])[2]["chosen"], [c])
        g = [[(a, 8, 1, "eligible")], [(b, 8, 1, "eligible")]]
        for ordered in (g, list(reversed(g))):
            self.assertEqual(resolve(ordered, [1])[1]["chosen"], [b])

    def test_exhaustive_small_states_and_global_selections(self):
        for states in product(("free", "eligible", "cold"), repeat=4):
            keys = [(0, 4), (0, 2), (0, 7), (0, 3)]
            rows = [
                (key, read, copy, s)
                for key, read, copy, s in zip(keys, (2, 2, 8, 5), (2, 2, 3, 6), states, strict=True)
            ]
            groups = [rows[:2], rows[2:]]
            outputs = resolve(groups, range(6))
            k0 = brute(groups, 0)[0]
            for k, out in outputs.items():
                cost, _, chosen = brute(groups, k)
                self.assertEqual(
                    out, dict(gain_us=k0 - cost, chosen=list(chosen), group_max_sum_us=cost)
                )

    def test_invalid_shapes_durations_and_temporal_states(self):
        good = ((1, 2), 1, 2, "eligible")
        for groups in (
            [[good] * 5],
            [[good, good]],
            [[good], [good]],
            [[((1, 2), 8, 1, "free")], [good]],
            [[good, ((0, 2), 1, 2, "cold")]],
            [[((1, 2), True, 2, "cold")]],
            [[((1, 128), 0, 0, "free")]],
            [[((1, 3), 1.5, 2, "free")]],
            [[((1, 2), 0, -1, "eligible")]],
            [[((1, 2), 0, 0, "unavailable")]],
        ):
            with self.assertRaises(ValueError):
                resolve(groups, [3])
        for k in (-1, True, 2.5):
            with self.assertRaises(ValueError):
                resolve([], [k])


if __name__ == "__main__":
    unittest.main()
