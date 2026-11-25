"""Independent cut projections distinguish changes invisible to a membership-only oracle."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("cut", Path(__file__).with_name("compare.py"))
cut = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cut)


def row(kind, expert=5, slot=3, worker=-1, claim=0):
    return cut.fd.Row(
        1,
        0,
        1,
        int(kind == "SLOT"),
        claim,
        0,
        cut.fd.NAMES.index(kind),
        1,
        1,
        0,
        0,
        expert,
        slot,
        worker,
        -1,
        -1,
        0,
        0,
    )


class TestCut(unittest.TestCase):
    def test_same_members_different_slot_or_generation(self):
        initial = [(e, 1, 2, 0) for e in range(40)]
        final = initial.copy()
        final[:2] = [(1, 2, 2, 0), (0, 1, 2, 0)]
        changes = cut.delta(cut.layer_view(initial, [], {}, 0), cut.layer_view(final, [], {}, 0))
        self.assertEqual(
            (changes["ready_members"], changes["slot_expert"], changes["slot_generation"]),
            (0, 2, 1),
        )

    def test_duplicate_fifo_claim_and_unidentified_inherited_worker(self):
        snapshot = row("SLOT", claim=1)
        key = cut.fd.identity(snapshot)
        self.assertEqual(cut.active_workers([snapshot]), {key: None})
        read = row("READ", worker=2)
        self.assertEqual(cut.active_workers([snapshot, read]), {key: 2})
        end = row("PUBLISH", worker=2)
        self.assertEqual(cut.active_workers([snapshot, read, end]), {})
        with self.assertRaisesRegex(ValueError, "without claim"):
            cut.active_workers([read])
        table = [(e, 1, 2, 0) for e in range(40)]
        table[3] = (5, 1, 1, 1)
        table[5] = (-1, 0, 0, 0)
        other = (0, 4, 2, 7)
        a = cut.layer_view(table, [key, key, other], {key: 2}, 0)
        b = cut.layer_view(table, [key, other, key, key], {key: 3}, 0)
        self.assertEqual((cut.delta(a, b)["fifo"], cut.delta(a, b)["active"]), (3, 1))
        self.assertEqual(
            cut.occupancy(a),
            {"active": 1, "ready": 38, "empty": 1, "loading": 1, "claimed": 1, "queued": 3},
        )


if __name__ == "__main__":
    unittest.main()
