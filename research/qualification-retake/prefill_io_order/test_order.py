import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

import measure


class TestQueue(unittest.TestCase):
    def setUp(self):
        self.groups = json.loads((measure.HERE / "schedule.json").read_text())["groups"]

    def test_four_threads_and_group(self):
        for g in self.groups:
            jobs = g["jobs"]
            n = sum(j["role"] == "demand" for j in jobs)
            fifo = measure.ordered_indices(jobs, "fifo")
            ordered = measure.ordered_indices(jobs, "sorted")
            self.assertNotEqual(fifo, ordered)
            self.assertEqual(fifo[n:], ordered[n:])
            self.assertEqual(sorted(fifo), sorted(ordered))

            def reader(fd, ranges, buffer):
                return [(time.monotonic_ns(), time.monotonic_ns()) for _ in ranges]

            with ThreadPoolExecutor(max_workers=4) as pool:
                receipt = measure.cohort(pool, None, jobs, [None] * len(jobs), "sorted", reader)
            self.assertEqual(receipt["order_indices"], ordered)
            self.assertEqual([j["expert"] for j in receipt["jobs"]], [j["expert"] for j in jobs])

    def test_short_job_fails(self):
        jobs = self.groups[0]["jobs"]
        with (
            ThreadPoolExecutor(max_workers=4) as pool,
            self.assertRaisesRegex(ValueError, "bad pread"),
        ):
            measure.cohort(pool, False, jobs, [None] * len(jobs), "fifo", lambda *_: [])

    def test_service_gate(self):
        def make(demand, worker, drain):
            return {
                "demand_ns": demand,
                "read_worker_ns": worker,
                "drain_ns": drain,
                "groups": [{"demand_ns": demand // 2}] * 2,
            }

        baseline = make(100, 200, 200)
        gain = make(90, 180, 200)
        service_only = make(99, 180, 200)
        bad_drain = make(90, 180, 220)
        self.assertEqual(measure.decision([baseline, gain, gain, baseline])[0], "GO")
        self.assertEqual(
            measure.decision([baseline, service_only, bad_drain, baseline])[0], "NO_GO"
        )
        self.assertEqual(measure.decision([baseline, gain, bad_drain, baseline])[0], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
