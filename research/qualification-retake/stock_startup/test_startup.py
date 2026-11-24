"""Directed model-free checks for the loader-only entry point."""

import argparse
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import start


class StartupTests(unittest.TestCase):
    def test_ready_is_after_listen_and_needs_placement_evidence(self):
        self.assertFalse(start.logged_geometry("listening on 127.0.0.1")["ready"])
        self.assertFalse(all(start.logged_geometry("model loaded").values()))
        text = """CPU_Mapped model buffer size = 1 MiB
        CUDA0 MoE cache size = 2000 MiB
        36 layers, mxfp4: 161 slots
        creating non-SWA KV cache, size = 8192 cells
        creating     SWA KV cache, size = 256 cells
        model loaded"""
        self.assertTrue(all(start.logged_geometry(text).values()))

    def test_empty_io_baseline_and_vma_device_inode(self):
        self.assertEqual(start.io_delta({}, {"8:0": {"rbytes": 4096}}), {"8:0": {"rbytes": 4096}})
        p = Path("/proc/self/exe")
        with ExitStack() as stack:
            actual = start.Reference(stack, p, start.sha(p)).key
            self.assertIn(actual, start.vm_objects(os.getpid()))
            self.assertEqual(start.PlacedFile(stack, p, start.identity(p)).key, actual)

    def test_invalid_scope_stops_before_opening_model_or_spawning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = argparse.Namespace(
                new_output=root / "output", new_raw=root / "private", policy=root / "policy"
            )
            a.policy.write_text("{}")
            res = {"cgroup": {}}
            with (
                patch.object(start, "cap_for", return_value=8 * start.GIB),
                patch.object(start.policy_api, "freeze_protocol_resource_limits", return_value=res),
                patch.object(start.policy_api, "validate_resource_protocol"),
                patch.object(start.bounded, "cgroup_state", return_value=None),
                patch.object(start.subprocess, "Popen") as popen,
            ):
                self.assertEqual(start.run(a), "NOT_RUN")
                popen.assert_not_called()
            r = json.loads((a.new_output / "receipt.json").read_text())
            self.assertEqual((r["server_starts"], r["reason"]), (0, "scope_limit"))

    def test_replaced_inode_rejected_even_at_equal_size(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            obj = Path(tmp) / "first"
            obj.write_bytes(bytes(8192))
            expected = start.identity(obj)
            ref = start.PlacedFile(stack, obj, expected)
            other = obj.with_name("other")
            other.write_bytes(bytes(8192))
            other.replace(obj)
            with self.assertRaisesRegex(ValueError, "placement_changed_at_mapping"):
                ref.verify()
            with self.assertRaisesRegex(ValueError, "placement_changed_at_mapping"):
                start.PlacedFile(stack, obj, expected)


if __name__ == "__main__":
    unittest.main()
