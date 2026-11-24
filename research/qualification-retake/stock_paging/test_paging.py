import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock_startup"))
import start  # noqa: E402


class PagingTests(unittest.TestCase):
    def test_high_reclaim_paths_have_distinct_controls(self):
        policy = start.read(
            start.HERE.parents[2] / "results/post-c195-epoch-20260930T223734Z/resource-policy.json"
        )
        cap = start.cap_for(policy, paging=True)
        self.assertEqual(cap, 10 * start.GIB)
        r = start.policy_api.freeze_protocol_resource_limits(
            policy,
            cgroup_memory_max_bytes=cap,
            start_mode="CAPACITY_ADMISSION_START",
            execution_class="FILE_PAGING",
        )
        resource = start.policy_api.validate_resource_protocol({"resources": r, "limits": {}})
        self.assertEqual(resource["cgroup"]["memory_high_bytes"], int(9.5 * start.GIB))
        self.assertIsNone(resource["cgroup"]["memory_stop_bytes"])
        self.assertFalse(start.at_preventive_limit(cap, cap, None))
        self.assertTrue(start.at_preventive_limit(cap, cap, cap - 512 * start.MIB))

    def test_smaps_keeps_only_numeric_aggregates(self):
        out = start.rollup_bytes(Path(f"/proc/{os.getpid()}/smaps_rollup").read_text())
        self.assertTrue(all(type(v) is int and v >= 0 for v in out.values()))
        self.assertGreater(out["Rss"], 0)
        self.assertGreater(out["Pss_File"], 0)
        with self.assertRaisesRegex(ValueError, "smaps_rollup_missing"):
            start.rollup_bytes("Rss: 10 kB\n")


if __name__ == "__main__":
    unittest.main()
