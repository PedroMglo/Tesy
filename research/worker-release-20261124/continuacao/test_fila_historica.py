import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fila_historica import StageQueue, terminal  # noqa: E402


class StageQueueTest(unittest.TestCase):
    def test_expired_reading_is_still_occupied_until_completion(self):
        q = StageQueue()
        for t in range(1, 5):
            q.event(t, 1)
        for t in range(1, 4):
            q.event(t, 2)
        q.event(2, 5)
        self.assertIsNone(q.next_ticket())
        self.assertTrue(q.event(1, 6))
        self.assertEqual(q.next_ticket(), 4)
        self.assertEqual(q.running, {1, 2, 3})
        self.assertEqual(q.pure, {2, 3})

    def test_reject_out_of_order_and_excess_dispatch(self):
        q = StageQueue()
        for t in range(1, 5):
            q.event(t, 1)
        with self.assertRaises(ValueError):
            q.event(2, 2)
        for t in range(1, 4):
            q.event(t, 2)
        with self.assertRaises(ValueError):
            q.event(4, 2)

    def test_ready_attach_is_not_a_release_opportunity(self):
        q = StageQueue()
        for kind in (1, 2, 3):
            q.event(1, kind)
        self.assertFalse(q.event(1, 6))

    def test_queued_removal_is_distinct_from_expiry_after_reading(self):
        self.assertEqual(terminal({1: (1, {}), 4: (2, {})}), "removed_queued")
        self.assertEqual(terminal({i: (i, {}) for i in (1, 2, 3, 4)}), "expired_ready")
        self.assertEqual(terminal({i: (i, {}) for i in (1, 2, 3, 4, 5)}), "expired_running")
