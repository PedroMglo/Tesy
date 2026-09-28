"""Directed regression for the C96 sequential-receipt prelaunch failure."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from c2_gate import GateError
from c97_server_wave_bridge import prior_control_passed


class ReceiptHandoff(unittest.TestCase):
    def test_candidate_requires_valid_prior_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'raw').mkdir()
            with self.assertRaises(GateError):
                prior_control_passed(root)
            path = root/'raw'/'control-receipt.json'
            good = {'schema':'c97-arm-receipt-v1', 'run_id':'c97-control01',
                    'status':'PASS_BRIDGE_TESTED_SCOPE', 'completed_requests':2,
                    'reason':None}
            path.write_text(json.dumps(good))
            self.assertEqual(prior_control_passed(root), good)
            for change in ({'status':'FAIL_RESOURCES_OR_EVIDENCE'},
                           {'completed_requests':1}, {'run_id':'c96-control01'}):
                path.write_text(json.dumps(dict(good, **change)))
                with self.assertRaises(GateError):
                    prior_control_passed(root)

    def test_prior_receipt_does_not_dirty_measurement_tree(self):
        repo = Path(__file__).resolve().parents[1]
        receipt = repo/'results/c97-session-wave-server-20260928T2133Z/raw/control-receipt.json'
        ignored = subprocess.run(['git','-C',str(repo),'check-ignore','-q',str(receipt)],
                                 check=False)
        self.assertEqual(ignored.returncode, 0)
        status = subprocess.check_output(['git','-C',str(repo),'status','--porcelain',
                                          '--untracked-files=all','--',str(receipt)],text=True)
        self.assertEqual(status, '')


if __name__ == '__main__':
    unittest.main()
