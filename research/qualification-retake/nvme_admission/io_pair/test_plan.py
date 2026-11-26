"""Directed model-free tests. All payloads here are fixtures."""

import ctypes
import json
import mmap
import unittest
from unittest.mock import patch

import run


class TestBoundedReads(unittest.TestCase):
    def test_clock_union(self):
        self.assertEqual(run.union_ns([(1, 4), (2, 5), (4, 7), (9, 11)]), 8)

    def test_short_read_stops_without_retry(self):
        with mmap.mmap(-1, 4096) as buf:
            ptr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
            with patch.object(run, "pread", return_value=1024) as pread:
                with self.assertRaisesRegex(OSError, "short/failed"):
                    run.one_job(1, [[32, 4000, 0, 4096]], [(buf, ptr)])
                pread.assert_called_once()

    def test_plan_counts_and_alignment(self):
        path = run.HERE / "plan.json"
        self.assertEqual(run.sha256(path), run.PLAN_SHA)
        plan = json.loads(path.read_text())
        jobs = [e for group in plan["groups"] for e in group["experts"]]
        self.assertEqual(len(jobs), 20)
        self.assertEqual(plan["component_order"], ["gate", "down", "up"])
        req = payload = 0
        for expert in jobs:
            for offset, size, base, count in expert["ranges"]:
                self.assertEqual((base % 4096, count % 4096), (0, 0))
                self.assertTrue(0 <= offset - base < 4096)
                self.assertTrue(0 <= count - (offset - base) - size < 4096)
                req += count
                payload += size
        self.assertEqual((req, payload), (264630272, 264384000))


if __name__ == "__main__":
    unittest.main()
