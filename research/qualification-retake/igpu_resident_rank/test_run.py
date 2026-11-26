"""Reject false provenance, stale generation and unsupported pointer types without Vulkan."""

import unittest
from pathlib import Path
from runpy import run_path

screen = run_path(Path(__file__).with_name("run.py"))
N = screen["PAYLOAD"] // 4


def synthetic():
    return "\n".join(
        (
            "scope_peak_bytes\t1024",
            "device\tAMD Radeon 890M\tradv\t0000:c5:00.0\t4098\t5390\t1\t4096",
            "heap\t0\t1073741824\t1",
            "type\t0\t0\t7",
            "heap\t1\t2000000000\t0",
            "type\t1\t1\t6",
            "queue\t0\t7",
            "external_features\t4",
            "providers\tRADV+loader+renderD128",
            "import\t13238272\t64\t2\t3\t1\t1\t6",
            "import\t13238272\t64\t2\t3\t1\t1\t6",
            f"generation\t1\t{N}\t{N}",
            f"generation\t2\t{N}\t{N}",
            "scope_peak_bytes\t54087680",
            "PASS_HOST_IMPORT_COPY_ONLY",
        )
    )


class HostImport(unittest.TestCase):
    def test_host_visible_device_local_and_actual_host_import_are_independent(self):
        proof = screen["review"](synthetic())
        self.assertEqual(proof["host_visible_device_local_types"], [0])
        self.assertFalse(proof["imports"][0]["imported_host_visible_device_local"])

    def test_faults(self):
        for correct, wrong in (
            ("c5:00.0", "c4:00.0"),
            ("renderD128", "renderD129"),
            ("queue\t0\t7", "queue\t0\t1"),
            ("13238272\t64\t2\t3", "13238272\t64\t1\t3"),
            (f"generation\t2\t{N}\t{N}", f"generation\t2\t0\t{N}"),
            ("54087680", "134217729"),
        ):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                screen["review"](synthetic().replace(correct, wrong))


if __name__ == "__main__":
    unittest.main()
