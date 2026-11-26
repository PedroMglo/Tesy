import unittest
from pathlib import Path
from runpy import run_path

p = run_path(str(Path(__file__).with_name("score.py")))


class Price(unittest.TestCase):
    def test_integer_capacity_and_alternative_read(self):
        payload = p["PAYLOAD"]
        pop = {"jobs": 3, "payload_bytes": 3 * payload, "read_floor_ns": 24_000_000}
        # 3 complete records at 8 GB/s minus one nanosecond fits 2.
        margin = 3 * payload // 8 - 1
        q = p["charges"](pop, margin)
        self.assertEqual(q["volume"]["8000000000"]["max_jobs_served_after_release"], 2)
        self.assertEqual(q["volume"]["8000000000"]["additional_ns"], 1)
        self.assertEqual(q["read_only"]["0.5x"]["floor_ns"], 12_000_000)
        self.assertGreater(q["required_Bps_for_all_payloads"], 8_000_000_000)
        with self.assertRaises(ValueError):
            p["charges"](pop | {"payload_bytes": 4}, margin)
