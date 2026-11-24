"""Model-free tests of observed barrier attribution and input identity."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from barreira.barrier import measure, run

A = (1, 2, 8, 3, 9)
B = (1, 2, 7, 1, 2)
C = (1, 2, 3, 2, 3)


def event(kind, us, work, route=1):
    return SimpleNamespace(kind=kind, us=us, work=work, call=work[0], layer=work[1], route=route)


def stream(publications):
    rows = [event(11, 1, A), event(5, 2, A), event(5, 7, B), event(5, 8, C)]
    rows += [event(10, when, w) for when, w in publications]
    return [*rows, event(12, 22, A)]


class ObservedBarrier(unittest.TestCase):
    def test_distinguishes_last_generation_and_two_gaps(self):
        for order, winner, terminal in [
            ([(9, C), (12, A), (20, B)], "fifo_head", 8),
            ([(9, C), (20, B), (20, A)], "blocked", None),
            ([(9, A), (12, B), (20, C)], "other", None),
            ([(9, A), (20, C), (20, B)], "fifo_head", 0),
        ]:
            with self.subTest(order=order):
                row = measure(stream(order), {3: A}, {3: B}, {3: "ABSENT"})["direct_read"]
                self.assertEqual(row["episodes"], row["distinct_barriers"])
                self.assertEqual(row["last_publication"], {winner: 1})
                durations = row["fifo_head_is_last"]
                if terminal is None:
                    self.assertTrue(all(value is None for value in durations.values()))
                else:
                    self.assertEqual(durations["accept_to_head_accept_us"]["median"], 5)
                    self.assertEqual(durations["last_minus_penultimate_publish_us"]["median"],
                                     terminal)

    def test_missing_barrier_cross_route_duplicate_and_waiting_heads(self):
        rows = stream([(10, C), (14, A), (19, B)])
        self.assertEqual(measure(rows, {3: A}, {3: B}, {3: "READING"})["any"]["episodes"], 0)
        with self.assertRaisesRegex(ValueError, "missing route wait"):
            measure(rows[:-1], {3: A}, {3: B}, {3: "QUEUED"})
        with self.assertRaisesRegex(ValueError, "repeated FIFO generation"):
            measure(rows, {3: A, 4: C}, {3: B, 4: B}, {3: "READY", 4: "READY"})
        rows[2].route = 7
        with self.assertRaisesRegex(ValueError, "different router barriers"):
            measure(rows, {3: A}, {3: B}, {3: "QUEUED"})

    def test_rejects_unpinned_receipt_before_traces_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "head.json"
            bad.write_text("{}")
            self.assertEqual(run(root, bad, root / "attempt"), 1)
            result = json.loads((root / "attempt/barrier.json").read_text())
            self.assertEqual(result["arms"], {})
            self.assertEqual(result["failure"], "unexpected head receipt")
            with self.assertRaises(FileExistsError):
                run(root, bad, root / "attempt")
