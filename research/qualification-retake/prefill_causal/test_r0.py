"""Counterexamples for the drained generation and publication boundaries."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prefill_causal import r0  # noqa: E402


def snapshot():
    layers = [
        dict(
            layer=i,
            native_cache_buffer=r0.TIERS[i],
            logical_bytes_per_load=r0.BYTES,
            slot_expert=[0] + [-1] * 39,
            slot_generation=[2] + [0] * 39,
            slot_state=[2] + [0] * 39,
            slot_claimed=[0] * 40,
        )
        for i in range(36)
    ]
    return dict(n_calls=90, pending_queue=0, n_miss=54, n_preload=18, layers=layers)


class Conservation(unittest.TestCase):
    def test_tiers_and_drained_counters(self):
        pools, counts = r0.snapshot_counts(snapshot(), 90)
        self.assertEqual(len(pools), 36)
        self.assertEqual([sum(counts[:25]), sum(counts[25:])], [50, 22])
        for field in ("pending_queue", "n_calls", "n_miss", "n_preload"):
            snap = snapshot()
            snap[field] += 1
            with self.assertRaises(ValueError):
                r0.snapshot_counts(snap, 90)

    def test_publication_and_generation(self):
        snap = snapshot()
        snap["layers"][0]["slot_generation"][1] = 1
        with self.assertRaisesRegex(ValueError, "generation history"):
            r0.snapshot_counts(snap, 90)
        initial, _ = r0.snapshot_counts(snapshot(), 90)
        end = [list(pool) for pool in initial]
        end[0][1] = (1, 1, 2, 0)
        records = [
            r0.boundary.HEADER,
            "4 0 0 0 0 1 1 1 0 0 0",
            "4 1 0 0 0 1 1 1 0 0 0",
            "10 3 0 0 0 1 1 1 0 0 0",
            "16 4 0 0 0 0 0 0 0 0 0",
        ]
        self.assertEqual(r0.per_phase(iter(records), initial, end), {("increment", 0): 1})
        with self.assertRaisesRegex(ValueError, "undrained"):
            r0.per_phase(iter(records[:3] + records[-1:]), initial, end)
        with self.assertRaisesRegex(ValueError, "generation jump"):
            r0.per_phase(iter([records[0], "4 0 0 0 0 1 1 2 0 0 0"]), initial, end)
