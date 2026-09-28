#!/usr/bin/env python3
import unittest

from host_resource_policy import (
    CPU_TJMAX_C,
    derive_policy,
    parse_nvidia_temperature_query,
    ResourcePolicyError,
)

SENSORS = {
    "k10temp-pci-00c3": {"Tctl": {"temp1_input": 48.25}},
    "nvme-pci-c100": {
        "Composite": {
            "temp1_input": 34.85,
            "temp1_max": 86.85,
            "temp1_crit": 89.85,
        },
        "Sensor 1": {
            "temp2_input": 34.85,
            "temp2_max": 65261.85,
        },
    }
}

GPU_Q = """
    Temperature
        GPU Current Temp                  : 44 C
        GPU Shutdown Temp                 : 97 C
        GPU Slowdown Temp                 : 92 C
        GPU Max Operating Temp            : 87 C
        GPU Target Temperature            : 83 C
"""


class ResourcePolicyTests(unittest.TestCase):
    def test_temperature_parse(self):
        row = parse_nvidia_temperature_query(GPU_Q)
        self.assertEqual(row["max_operating_c"], 87)
        self.assertEqual(row["slowdown_c"], 92)
        self.assertEqual(row["shutdown_c"], 97)

    def test_derive_uses_device_and_admission_limits(self):
        policy = derive_policy(
            memory={"MemTotal": 32698777600, "MemAvailable": 23675543552},
            gpu_csv="NVIDIA GeForce RTX 4060 Laptop GPU, 8188, 12, 44, 615.71.09",
            sensors=SENSORS,
            nvidia_temperature_query=GPU_Q,
        )
        self.assertEqual(policy["cpu"]["device_limit_c"], CPU_TJMAX_C)
        self.assertEqual(policy["gpu"]["memory_admission_max_mib"], 8188 - 512)
        self.assertEqual(policy["gpu"]["warning_c"], 87)
        self.assertEqual(policy["gpu"]["stop_c"], 92)
        self.assertEqual(policy["nvme"]["warning_c"], 86.85)
        self.assertEqual(policy["nvme"]["critical_c"], 89.85)
        self.assertEqual(policy["memory"]["host_reserve_bytes"], 2 * 2**30)
        self.assertGreater(policy["memory"]["suggested_cgroup_max_bytes"], 18 * 2**30)

    def test_implausible_secondary_nvme_threshold_is_ignored(self):
        policy = derive_policy(
            memory={"MemTotal": 32698777600, "MemAvailable": 23675543552},
            gpu_csv="GPU, 8188, 12, 44, 1",
            sensors=SENSORS,
            nvidia_temperature_query=GPU_Q,
        )
        self.assertEqual(policy["nvme"]["critical_c"], 89.85)

    def test_missing_usable_composite_fails_closed(self):
        with self.assertRaises(ResourcePolicyError):
            derive_policy(
                memory={"MemTotal": 32698777600, "MemAvailable": 23675543552},
                gpu_csv="GPU, 8188, 12, 44, 1",
                sensors={"nvme-pci-c100": {"Sensor 1": {"temp2_input": 35}}},
                nvidia_temperature_query=GPU_Q,
            )


if __name__ == "__main__":
    unittest.main()
