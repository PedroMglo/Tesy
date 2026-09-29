from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from c2_gate import GateError
from c118_start_inventory import collect, require_inventory, validate_sample
from run_bounded import sha256


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

    def test_prospective_receipt_and_adversarial_rows(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "raw").mkdir()
            clock = [0.0]
            def sample():
                if clock[0] == 0:
                    clock[0] += .01  # a normal delay before the first reading
                return observation()
            def sleep(seconds):
                clock[0] += seconds
            utc_base = datetime.fromisoformat("2026-09-29T12:00:00+00:00")
            receipt = collect(root, "arm-2", policy=POLICY, cap_bytes=10_000,
                              expected_power=POWER, sample=sample,
                              monotonic=lambda: clock[0], sleep=sleep, duration_s=2,
                              utc_now=lambda: utc_base + timedelta(seconds=clock[0]))
            path = root / "raw/arm-2.start-inventory.jsonl"
            original = [json.loads(line) for line in path.read_text().splitlines()]
            now = datetime.fromisoformat(original[-1]["utc"]) + timedelta(seconds=1)
            self.assertEqual(require_inventory(root, "arm-2", receipt, policy=POLICY,
                                               cap_bytes=10_000, expected_power=POWER,
                                               duration_s=2, now=now), 3)

            def reject(rows, match):
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                changed = {**receipt, "sha256": sha256(path)}
                with self.assertRaisesRegex(GateError, match):
                    require_inventory(root, "arm-2", changed, policy=POLICY,
                                      cap_bytes=10_000, expected_power=POWER,
                                      duration_s=2, now=now)

            rows = deepcopy(original)
            rows[1].pop("observation")
            reject(rows, "observation missing")
            rows = deepcopy(original)
            rows[1]["run_id"] = "arm-1"
            reject(rows, "arm identity")
            rows = deepcopy(original)
            for i, row in enumerate(rows):
                row["utc"] = (datetime.fromisoformat("2020-01-01T00:00:00+00:00") +
                              timedelta(seconds=i)).isoformat()
            reject(rows, "stale")
            rows = deepcopy(original)
            rows[1]["observation"]["thermal"]["cpu_tctl_c"] = 120
            reject(rows, "resource admission")
            rows = deepcopy(original)
            rows[1]["observation"]["power"]["source"] = "BATTERY"
            reject(rows, "AC/profile")
            path.write_text("".join(json.dumps(row) + "\n" for row in original) + "\n")
            with self.assertRaisesRegex(GateError, "identity/hash"):
                require_inventory(root, "arm-2", receipt, policy=POLICY,
                                  cap_bytes=10_000, expected_power=POWER,
                                  duration_s=2, now=now)
            path.write_text("".join(json.dumps(row) + "\n" for row in original))
            with self.assertRaisesRegex(GateError, "identity/hash"):
                require_inventory(root, "arm-2", {**receipt, "cap_bytes": 20_000},
                                  policy=POLICY, cap_bytes=10_000,
                                  expected_power=POWER, duration_s=2, now=now)

    def test_terminal_sampling_delay_and_second_nvme(self):
        policy = deepcopy(POLICY)
        policy["nvme"].append({"sensor": "nvme-second", "stop_c": 70})
        bad = observation()
        bad["thermal"]["nvme_composite_by_sensor"]["nvme-second"] = 71
        with self.assertRaisesRegex(GateError, "resource admission"):
            validate_sample(bad, policy=policy, cap_bytes=10_000,
                            expected_power=POWER)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "raw").mkdir()
            clock = [0.0]
            def sample():
                if clock[0] >= 2:
                    clock[0] += 5
                return observation()
            def sleep(seconds):
                clock[0] += seconds
            with self.assertRaisesRegex(GateError, "cadence gap"):
                collect(root, "slow-final", policy=POLICY, cap_bytes=10_000,
                        expected_power=POWER, sample=sample,
                        monotonic=lambda: clock[0], sleep=sleep, duration_s=2)


if __name__ == "__main__":
    unittest.main()
