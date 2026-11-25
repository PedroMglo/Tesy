import sys
import unittest
from itertools import combinations, product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from l2_read_admission.oracle import bounds, maximum_hits  # noqa: E402


def enumerate_intervals(intervals, k):
    for length in range(len(intervals), 0, -1):
        for kept in combinations(intervals, length):
            if all(sum(s <= time < e for s, e in kept) <= k for time, _ in kept):
                return length
    return 0


def brute_events(raw, cut, k):
    """Explore every retention/eviction subset at each P10; charge the selected P5 hits."""
    events = sorted([(s, False, key) for s, _, key in raw] + [(e, True, key) for _, e, key in raw])
    scores = {frozenset(): 0}
    for pos, published, key in events:
        if not published:
            scores = {
                state: score + int(pos >= cut and key in state) for state, score in scores.items()
            }
            continue
        alternatives = {}
        for state, score in scores.items():
            eligible = state | {key}
            for n in range(min(k, len(eligible)) + 1):
                for selected in combinations(eligible, n):
                    new = frozenset(selected)
                    alternatives[new] = max(alternatives.get(new, 0), score)
        scores = alternatives
    return max(scores.values())


class OptionalPublication(unittest.TestCase):
    def test_against_exhaustive_selection_including_overlaps_and_equal_endpoints(self):
        shapes = list(combinations(range(5), 2))
        for intervals in combinations(shapes, 4):
            for k in (0, 1, 2, 3, 4):
                self.assertEqual(maximum_hits(intervals, k), enumerate_intervals(intervals, k))
        self.assertEqual(maximum_hits([(1, 4), (1, 4), (1, 4)], 2), 2)

    def test_all_retention_choices_at_serial_publications_and_different_cuts(self):
        for keys in product(range(3), repeat=4):
            rows = [(2 * i, 2 * i + 1, (0, k)) for i, k in enumerate(keys)]
            for cut in range(len(rows) + 1):
                for capacity in (0, 1, 2):
                    actual = bounds(rows[:cut], rows[cut:], capacity)
                    self.assertEqual(actual["joint_hits"], brute_events(rows, 0, capacity))
                    self.assertEqual(
                        actual["decode_only_hits"], brute_events(rows, 2 * cut, capacity)
                    )

    def test_early_claim_must_not_consume_l2_until_publication(self):
        a, b = (0, 2), (1, 2)
        rows = [(1, 6, a), (2, 3, b), (4, 5, b), (7, 8, a)]
        self.assertEqual(maximum_hits([(1, 7), (2, 4)], 1), 1)  # slot charged prematurely at P5
        self.assertEqual(bounds([], rows, 1)["decode_only_hits"], 2)
        self.assertEqual(brute_events(rows, 0, 1), 2)

    def test_maxima_can_require_different_states_at_i(self):
        keys = [1, 0, 0, 0, 0, 1]
        rows = [(2 * i, 2 * i + 1, (0, k)) for i, k in enumerate(keys)]
        actual = bounds(rows[:-1], rows[-1:], 1)
        self.assertEqual((actual["joint_hits"], actual["decode_only_hits"]), (3, 1))
        self.assertEqual(actual["distinct_seen_at_I"], 2)

    def test_bad_same_key_overlap_duplicate_event_undrained_i_and_order(self):
        a, b = (0, 2), (1, 2)
        for before, after in (
            ([(0, 5, a), (1, 2, a)], []),
            ([(0, 5, a), (1, 5, b)], []),
            ([(0, 5, a)], [(1, 6, b)]),
            ([(1, 2, a), (0, 4, b)], []),
            ([(0, 0, a)], []),
            ([(0, 1, (1, 128))], []),
        ):
            with self.assertRaises(ValueError):
                bounds(before, after, 1)
        for capacity in (-1, True, 0.5):
            with self.assertRaises(ValueError):
                bounds([], [], capacity)
        self.assertEqual(bounds([], [], 0)["joint_hits"], 0)


if __name__ == "__main__":
    unittest.main()
