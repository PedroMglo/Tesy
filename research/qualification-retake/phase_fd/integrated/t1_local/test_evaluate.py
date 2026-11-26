import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "local_prices_tested", Path(__file__).with_name("evaluate.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def snapshot(victims, expanded):
    return dict(evicted_ready=victims, all_available=expanded)


class LocalPrice(unittest.TestCase):
    def test_capacity_and_clock_dominance_both_scales(self):
        key, other = (2, 4), (3, 2)
        groups = [[(key, 1000)], [(other, 2000)]]
        populations = snapshot([key], [key, other])
        generous = {"47": 2 * m.replay.T, "46": 2 * m.replay.T}
        closed = m.opportunities(groups, populations, {key}, 10**10 - 1500, generous)
        self.assertTrue(m.dominated(closed))
        expanded = next(x for x in closed["all_available"]["rows"] if x["capacity"] == 353)
        self.assertEqual(
            expanded["scales"]["1/1"]["decisions"]["47"], "HEADROOM_ONLY_CAUSAL_POLICY_REQUIRED"
        )
        tight = m.opportunities(groups, populations, {key}, 10**10 - 1700, generous)
        self.assertFalse(m.dominated(tight))
        possible = next(x for x in tight["evicted_ready"]["rows"] if x["capacity"] == 353)
        self.assertEqual(possible["remaining_service_floor_ns"], 2000)
        self.assertEqual(possible["scales"]["4/5"]["first_floor_ns"], 10**10 - 100)
        self.assertNotIn("ordered_keys", repr(tight))

    def test_opportunity_uses_reachable_volume_same_pool(self):
        key, other = (0, 5), (1, 0)
        groups = [[(key, 42)]]
        table = m.opportunities(
            groups, snapshot([key], [key, other]), {key, other}, 0, {"47": 0, "46": m.replay.T}
        )
        self.assertTrue(m.dominated(table))
        row = next(x for x in table["evicted_ready"]["rows"] if x["capacity"] == 353)
        self.assertEqual(
            row["scales"]["1/1"]["decisions"]["46"], "HEADROOM_ONLY_CAUSAL_POLICY_REQUIRED"
        )
        with self.assertRaises(ValueError):
            m.opportunities(groups, snapshot([key], []), {key}, 0, {"47": 0})
        with self.assertRaises(ValueError):
            m.opportunities(groups, snapshot([key, key], [key]), {key}, 0, {"47": 0})

    def test_only_strict_dominance_suppresses_votes(self):
        def votes(a, b):
            return m.dominated(
                {
                    "evicted_ready": {
                        "rows": [
                            {
                                "capacity": 353,
                                "scales": {
                                    "1/1": {"decisions": {"47": a}},
                                    "4/5": {"decisions": {"47": b}},
                                },
                            }
                        ]
                    }
                }
            )

        self.assertFalse(votes(m.CLOSED, "INCONCLUSIVE_VOLUME_TRADEOFF"))
        self.assertTrue(votes(m.CLOSED, m.CLOSED))

    def test_initial_copies_are_counted_once_after_hit(self):
        # A single seeded expert is consumed once in decode. The earlier T1
        # installation that failed to survive to T2 must remain in the wasted count.
        keys = [[0, 1], [27, 3]]
        bank = {
            "ordered_keys": keys,
            "ordered_keys_sha256": m.opportunity.source.digest(keys),
            "tier": {
                "cpu": {"surviving": 1, "installs": 2, "discarded_in_t1": 1},
                "cuda": {"surviving": 1, "installs": 1},
            },
        }
        proto = m.replay.fd.Row(*([0] * len(m.replay.fd.Row._fields)))

        def e(kind, **fields):
            return proto._replace(kind=kind, **fields)

        rows = [
            e(5, expert=-1),
            e(11, expert=1, a=-1, gen=1, call=3),
            e(13, expert=1, gen=1, call=3),
            e(17, expert=1, gen=1, call=3),
        ]
        with patch.object(m, "CAPACITY", 2):
            for family in ("publication", "victims"):
                costs = m.t1_copy_report(
                    rows, family, bank, {"decode_hits": 1, "remaining_prefill_bytes": 0}
                )
                self.assertEqual(costs["cpu"]["useful_through_t2"], 1)
                self.assertEqual(costs["cpu"]["unused_through_t2"], 1)
                self.assertEqual(costs["cuda"]["unused_bytes"], m.replay.T)


if __name__ == "__main__":
    unittest.main()
