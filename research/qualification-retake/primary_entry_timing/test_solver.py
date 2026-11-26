import itertools
import random
import unittest
from collections import Counter

from solver import solve


def caps(**limits):
    result = [0] * 36
    for layer, cap in limits.items():
        result[int(layer)] = cap
    return result


def brute(groups, limits, allowed, fixed, n, d):
    keys = sorted({(layer, e) for layer, jobs in groups for e in jobs} & allowed)
    best = {}
    for size in range(len(keys) + 1):
        for subset in itertools.combinations(keys, size):
            count = Counter(layer for layer, _ in subset)
            if any(v > limits[layer] for layer, v in count.items()):
                continue
            read = sum(
                max((v for e, v in jobs.items() if (layer, e) not in subset), default=0)
                for layer, jobs in groups
            )
            old = best.get(size)
            if old is None or (read, subset) < old:
                best[size] = (read, subset)
    floor = min(read for read, _ in best.values())
    fit = [k for k, (r, _) in best.items() if 3 * (fixed * d + n * r) <= 16_000_000 * d]
    k = min(fit) if fit else min(k for k, (r, _) in best.items() if r == floor)
    r, picked = best[k]
    return dict(
        reaches=bool(fit),
        k=k,
        chosen=list(picked),
        remaining_us=r,
        k_minus_one_remaining_us=best[k - 1][0] if k else None,
        maximum_gain_us=best[0][0] - floor,
    )


class InitialPlacement(unittest.TestCase):
    def test_complementarity_and_certificate(self):
        # The two branches of length 19 require two slots together for any gain.
        groups = [(0, {5: 19, 7: 19}), (1, {8: 3, 9: 1}), (0, {11: 0})]
        free = {(0, 5), (0, 7), (1, 8), (1, 9), (0, 11)}
        limits = caps(**{"0": 2, "1": 2})
        answer = solve(groups, limits, free, 5_333_330, 1, 1)
        self.assertEqual(answer, brute(groups, limits, free, 5_333_330, 1, 1))
        self.assertEqual(answer["chosen"], [(0, 5), (0, 7)])
        self.assertEqual(
            (answer["remaining_us"], answer["k_minus_one_remaining_us"]), (3, 20)
        )

    def test_no_cross_layer_donation_and_minimal_maximum(self):
        group = [(0, {3: 17, 4: 17}), (1, {2: 0})]
        free = {(0, 3), (0, 4), (1, 2), (2, 5)}
        for limited in [caps(**{"0": 1, "1": 7}), caps()]:
            result = solve(group, limited, free, 5_333_333, 1, 1)
            self.assertFalse(result["reaches"])
            self.assertEqual(
                (result["k"], result["maximum_gain_us"], result["chosen"]), (0, 0, [])
            )
            self.assertIsNone(result["k_minus_one_remaining_us"])
        limited = caps(**{"0": 2, "1": 7})
        result = solve(group, limited, free, 5_333_334, 1, 1)
        self.assertFalse(result["reaches"])
        self.assertEqual(result["chosen"], [(0, 3), (0, 4)])
        self.assertEqual(
            (result["remaining_us"], result["k_minus_one_remaining_us"]), (0, 17)
        )

    def test_lexicographic_ties_across_layers_and_barriers(self):
        group = [(2, {9: 10}), (2, {2: 10}), (0, {33: 10}), (0, {75: 10})]
        free = {(layer, e) for layer, j in group for e in j}
        lim = caps(**{"0": 1, "2": 1})
        r = solve(group, lim, free, 5_333_313, 1, 1)
        self.assertEqual(r["chosen"], [(0, 33), (2, 2)])
        self.assertEqual(
            r, solve(reversed(group), lim, reversed(sorted(free)), 5_333_313, 1, 1)
        )

    def test_integer_equality_without_rounding(self):
        r = solve([(0, {0: 1})], [0] * 36, set(), 5_333_333, 1, 3)
        self.assertTrue(r["reaches"])
        self.assertEqual(r["k"], 0)
        r = solve([(0, {0: 1})], [0] * 36, set(), 5_333_333, 2, 3)
        self.assertFalse(r["reaches"])
        self.assertEqual((r["k"], r["remaining_us"]), (0, 1))

    def test_complete_enumeration(self):
        rng = random.Random(48721)
        for _ in range(150):
            groups = []
            used = Counter()
            for _ in range(5):
                layer = rng.randrange(3)
                width = rng.randrange(3)
                jobs = {
                    e: rng.randrange(7) for e in range(used[layer], used[layer] + width)
                }
                used[layer] += width
                groups.append((layer, jobs))
            allowed = {(layer, e) for layer, j in groups for e in j if rng.randrange(4)}
            limits = [rng.randrange(5) for _ in range(3)] + [0] * 33
            n, d = rng.choice([(1, 1), (4, 5)])
            fixed = 5_333_334 - rng.randrange(22)
            self.assertEqual(
                solve(groups, limits, allowed, fixed, n, d),
                brute(groups, limits, allowed, fixed, n, d),
            )

    def test_invalid_claims_and_units(self):
        for groups, limits, eligible, fixed, num, den in [
            ([(1, {2: 10}), (1, {2: 0})], [2] * 36, set(), 0, 1, 1),
            ([(1, {200: 0})], [2] * 36, set(), 0, 1, 1),
            ([(1, {i: 1 for i in range(5)})], [2] * 36, set(), 0, 1, 1),
            ([(1, {2: True})], [2] * 36, set(), 0, 1, 1),
            ([(1, {2: 1})], [2] * 35, {(1, 2)}, 0, 1, 1),
            ([], [-1] * 36, set(), 0, 1, 1),
            ([], [1] * 36, {(True, 1)}, 0, 1, 1),
            ([], [1] * 36, set(), 0, 1, 0),
        ]:
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                solve(groups, limits, eligible, fixed, num, den)
