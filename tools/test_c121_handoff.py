from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import c121_nominal_server as next_campaign
from c2_gate import strict_json


class TestC121Handoff(unittest.TestCase):
    def test_wrong_measurement_sha_fails_before_inventory_or_model(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "raw").mkdir()
            with patch.object(next_campaign.campaign, "budget", return_value={}), \
                 patch.object(next_campaign.campaign.base, "git",
                              return_value="a" * 40), \
                 patch.object(next_campaign.campaign.server, "run") as launch:
                code = next_campaign.campaign.run(
                    root, next_campaign.campaign.ORDER[0], "b" * 40)
            self.assertEqual(code, 1)
            launch.assert_not_called()
            receipt = strict_json((root / "raw/c121-p1-control.receipt.json").read_text())
            self.assertEqual(receipt["status"], "FAIL_HARNESS_PREMODEL")
            self.assertIn("measurement SHA mismatch", receipt["reason"])
            self.assertFalse(receipt["model_launch_observed"])
            self.assertIsNone(receipt["start_inventory_receipt_sha256"])


if __name__ == "__main__":
    unittest.main()
