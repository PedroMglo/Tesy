import itertools
import unittest

from oracle import farthest, snapshots, wave_pins


def best(initial, requests, capacity):
    # Exhaustively enumerate every legal set of survivors. Meant for tiny fixtures.
    costs = {frozenset(initial): 0}
    for req in requests:
        nxt = {}
        for state, cost in costs.items():
            missing = len(req - state)
            keepable = state - req
            for count in range(min(capacity - len(req), len(keepable)) + 1):
                for leftover in itertools.combinations(keepable, count):
                    after = frozenset(req.union(leftover))
                    nxt[after] = min(nxt.get(after, 10**9), cost + missing)
        costs = nxt
    return min(costs.values())


class TestOracle(unittest.TestCase):
    def test_batched_belady_matches_exhaustive(self):
        choices = [{0}, {0, 1}, {1, 2}, {2, 3}, {1}, {3}]
        for start in [{2}, {0, 1, 2}]:
            for req in itertools.product(choices, repeat=4):
                self.assertEqual(sum(map(len, farthest(start, req, 3))), best(start, req, 3))

    def test_witness_not_extrapolated_across_replacement(self):
        def r(kind, call, expert, slot, state, victim=-1):
            return dict(
                kind=kind,
                call_id=call,
                layer=0,
                expert=expert,
                slot=slot,
                state=state,
                victim=victim,
            )

        rows = [
            r("DEMAND", 1, 4, 6, 2),
            r("CALL_BEGIN", 2, -1, -1, -1),
            r("EVICT", 2, 7, 1, 2, 8),
            r("RESERVE", 2, 8, 1, -1),
            r("CALL_END", 2, -1, -1, -1),
            r("EVICT", 3, 9, 2, 2, 0),
            r("RESERVE", 3, 0, 2, -1),
        ]
        a, b = snapshots(rows)
        self.assertEqual(a[0][:4], [None, 7, 9, None])
        self.assertEqual(b[0][:4], [None, 8, 9, None])
        self.assertEqual((a[0][6], b[0][6]), (4, 4))

    def test_wave_parking_source(self):
        waves = [((0, 0), [0, 1, 2, 3]), ((0, 1), [4, 5]), ((1, 0), [1, 2, 3, 4])]
        self.assertEqual(
            wave_pins(waves, preload=True), [{0, 1, 2, 3, 4, 5}, {0, 1, 4, 5}, {1, 2, 3, 4}]
        )


class TestPlacement(unittest.TestCase):
    def test_cycle_charges_a_read_and_a_copy(self):
        from oracle import place

        report = place([4, 8], [8, 4], [], "lru")
        self.assertEqual(report["logical_loads"], 0)
        self.assertEqual(report["extra_restoration_reads"], 1)
        self.assertEqual(report["same_tier_slot_copies"], 1)

    def test_lru_victim_order_changes_boundary_costs(self):
        from oracle import place

        waves = [((0, -1), [2]), ((1, -1), [1])]
        low = place([0, 1], [0, 1], waves, "lru", oldest_highest=False)
        high = place([0, 1], [0, 1], waves, "lru", oldest_highest=True)
        self.assertEqual(low["logical_loads"] - low["endset_reads"], 1)
        self.assertEqual(high["logical_loads"] - high["endset_reads"], 2)
