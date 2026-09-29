from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from c2_gate import GateError
from c118_start_inventory import collect, validate_sample


POLICY = {"cpu": {"stop_c": 100},
          "gpu": {"uuid": "GPU-test", "stop_c": 89,
                  "memory_stop_total_mib": 7676},
          "nvme": [{"sensor": "nvme-test", "stop_c": 87}],
          "memory": {"reserve_bytes": 2_000}}
POWER = {"source": "AC", "profile": "performance"}


def observation():
    return {"thermal": {"cpu_tctl_c": 50,
                        "nvme_composite_by_sensor": {"nvme-test": 40}},
            "gpu": {"uuid": "GPU-test", "temperature_c": 45, "used_mib": 12},
            "power": POWER, "mem_available_bytes": 20_000}


class TestStartInventory(unittest.TestCase):
    def test_complete_and_mutants(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "raw").mkdir()
            clock = [0.0]
            def sleep(seconds):
                clock[0] += seconds
            row = collect(root, "good", policy=POLICY, cap_bytes=10_000,
                          expected_power=POWER, sample=observation,
                          monotonic=lambda: clock[0], sleep=sleep, duration_s=2)
            self.assertEqual(row["sample_count"], 3)
            self.assertEqual(len((root / "raw/good.start-inventory.jsonl").read_text().splitlines()), 3)
            with self.assertRaises(FileExistsError):
                collect(root, "good", policy=POLICY, cap_bytes=10_000,
                        expected_power=POWER, sample=observation,
                        monotonic=lambda: clock[0], sleep=sleep, duration_s=2)
            clock[0] = 0.0
            with self.assertRaisesRegex(GateError, "cadence gap"):
                collect(root, "gap", policy=POLICY, cap_bytes=10_000,
                        expected_power=POWER, sample=observation,
                        monotonic=lambda: clock[0], sleep=lambda _: sleep(2), duration_s=2)
            bad = observation()
            bad["gpu"]["temperature_c"] = 89
            with self.assertRaisesRegex(GateError, "resource admission"):
                validate_sample(bad, policy=POLICY, cap_bytes=10_000,
                                expected_power=POWER)
            bad = observation()
            bad["power"] = {"source": "BATTERY", "profile": "performance"}
            with self.assertRaisesRegex(GateError, "AC/profile"):
                validate_sample(bad, policy=POLICY, cap_bytes=10_000,
                                expected_power=POWER)
            bad = observation()
            del bad["gpu"]["uuid"]
            with self.assertRaisesRegex(GateError, "essential sensor missing"):
                validate_sample(bad, policy=POLICY, cap_bytes=10_000,
                                expected_power=POWER)


if __name__ == "__main__":
    unittest.main()
