#!/usr/bin/env python3
import unittest

from c9_server_admission import apply_prospective_resource_policy
from host_resource_policy import (
    CPU_TJMAX_C,
    derive_policy,
    freeze_protocol_resource_limits,
    operational_session_ready,
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
        self.assertEqual(policy["gpu"]["stop_c"], 96)
        self.assertEqual(policy["nvme"]["warning_c"], 86.85)
        self.assertEqual(policy["nvme"]["critical_c"], 89.85)
        self.assertEqual(policy["memory"]["host_reserve_bytes"], 2 * 2**30)
        self.assertGreater(policy["memory"]["suggested_cgroup_max_bytes"], 18 * 2**30)

    def test_freeze_protocol_limits_uses_policy_not_legacy_guards(self):
        policy = derive_policy(
            memory={"MemTotal": 32698777600, "MemAvailable": 23675543552},
            gpu_csv="GPU, 8188, 12, 44, 1",
            sensors=SENSORS,
            nvidia_temperature_query=GPU_Q,
        )
        limits = freeze_protocol_resource_limits(policy, cgroup_memory_max_bytes=20 * 2**30)
        self.assertEqual(limits["cpu_max_c"], 100)
        self.assertEqual(limits["gpu_max_mib"], 7676)
        self.assertEqual(limits["gpu_max_c"], 96)
        self.assertEqual(limits["nvme_max_c"], 89.85)
        self.assertEqual(limits["min_mem_available_bytes"], 2 * 2**30)
        self.assertEqual(limits["rss_max_bytes"], 32698777600)


    def test_apply_prospective_protocol_policy(self):
        policy = derive_policy(
            memory={"MemTotal": 32698777600, "MemAvailable": 23675543552},
            gpu_csv="GPU, 8188, 12, 44, 1",
            sensors=SENSORS,
            nvidia_temperature_query=GPU_Q,
        )
        protocol = {
            "limits": {
                "memory_max_bytes": 1, "rss_max_bytes": 1,
                "gpu_max_mib": 1, "min_mem_available_bytes": 1,
                "cpu_max_c": 1, "gpu_max_c": 1, "nvme_max_c": 1,
                "max_gap_s": 3, "boundary_s": 2,
                "min_elapsed_s": 0, "min_active_s": 0,
                "min_decode_s": 0, "min_decode_tok_s": 0,
                "min_last_half_tok_s": 0,
            },
            "c9": {},
        }
        out = apply_prospective_resource_policy(
            protocol, {"resource_policy": policy},
            cgroup_memory_max_bytes=20 * 2**30)
        self.assertEqual(out["c9"]["cgroup_memory_max_bytes"], 20 * 2**30)
        self.assertEqual(out["limits"]["cpu_max_c"], 100)
        self.assertEqual(out["limits"]["gpu_max_mib"], 7676)
        self.assertEqual(out["limits"]["min_mem_available_bytes"], 2 * 2**30)
        self.assertEqual(out["limits"]["memory_max_bytes"], 20 * 2**30 - 512 * 2**20)


    def test_operational_session_start_uses_warnings_not_cold_band(self):
        policy = derive_policy(
            memory={"MemTotal": 32698777600, "MemAvailable": 23675543552},
            gpu_csv="GPU, 8188, 12, 70, 1",
            sensors=SENSORS,
            nvidia_temperature_query=GPU_Q,
        )
        policy["cpu"]["current_c"] = 90
        policy["nvme"]["current_c"] = 60
        ok, reasons = operational_session_ready(policy)
        self.assertTrue(ok, reasons)
        policy["cpu"]["current_c"] = 95
        ok, reasons = operational_session_ready(policy)
        self.assertFalse(ok)
        self.assertIn("cpu-warning-at-start", reasons)

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
