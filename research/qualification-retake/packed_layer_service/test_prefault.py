"""Check required counters without running a child or querying the host."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "service_supervisor", Path(__file__).with_name("profile.py")
)
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


class Pretouch(unittest.TestCase):
    def test_complete_process_counts(self):
        fields = dict(
            scope="RUSAGE_SELF",
            minflt_before=824,
            minflt_after=51873,
            minflt_delta=51049,
            majflt_before=0,
            majflt_after=0,
            majflt_delta=0,
        )
        self.assertEqual(supervisor.prefault_telemetry({"prefault_faults": fields}), fields)
        for change in [
            {"scope": "RUSAGE_THREAD"},
            {"majflt_before": 1},
            {"minflt_delta": True},
            {"minflt_delta": -1},
            {"minflt_delta": 0},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                supervisor.prefault_telemetry({"prefault_faults": fields | change})

    def test_old_receipt_stays_failed(self):
        with self.assertRaises(ValueError):
            supervisor.prefault_telemetry({"prefault_ns": 123, "prefault_bytes": 528875520})
