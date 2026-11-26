import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report  # noqa: E402


class ReportTests(unittest.TestCase):
    def test_stop_before_on_and_no_preparation_as_physical(self):
        receipt = {
            "status": "FAIL_PRESERVED",
            "unexecuted_arms": ["ON"],
            "model_launch_receipts": 0,
            "arms": [{"mode": "OFF", "status": "FAIL_PRESERVED"}],
        }
        self.assertEqual(report.phases(receipt), receipt["arms"])
        for update in (
            {"status": "PREPARED_ONLY"},
            {"status": report.SUCCESS},
            {"unexecuted_arms": []},
            {
                "arms": receipt["arms"] + [{"mode": "ON", "status": "PASS_C292_ON"}],
                "unexecuted_arms": [],
            },
        ):
            with self.assertRaises(ValueError):
                report.phases(receipt | update)

    def test_unlaunched_failure_cannot_claim_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = {"model_launch_receipts": 0}
            self.assertEqual(report.observed_failure(root, record, "unit")["raw_files"], 0)
            raw = root / "raw"
            raw.mkdir()
            (raw / "unit.launch.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "launch evidence"):
                report.observed_failure(root, record, "unit")
            evidence = report.observed_failure(root, {"model_launch_receipts": 1}, "unit")
            self.assertEqual(set(evidence["observed_file_sha256"]), {"launch"})


if __name__ == "__main__":
    unittest.main()
