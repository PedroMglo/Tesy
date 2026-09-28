import copy
import unittest
from unittest.mock import patch

from c2_gate import GateError
import c87_file_charge_analysis as c87


class FileChargeAnalysisTests(unittest.TestCase):
    def test_hash_verified_historical_control(self):
        result = c87.analyze()
        self.assertTrue(result['same_backend_binary_model_profile_call_plan'])
        self.assertEqual(result['parent_status']['C78'], 'FAIL_RESOURCES_OR_EVIDENCE')
        self.assertGreater(result['at_14s_delta_C78_minus_C76b_bytes']['file_bytes'], 0)

    def test_tampered_samples_rejected(self):
        name = 'C78'
        root, relative = c87.PARENTS[name]
        with patch.dict(c87.PARENTS, {name: (root, 'protocol.json')}):
            with self.assertRaisesRegex(GateError, 'raw/manifest/protocol hash mismatch'):
                c87.parent(name)

    def test_profile_mismatch_rejected(self):
        original = c87.parent

        def changed(name):
            data = original(name)
            if name == 'C78':
                profile = copy.deepcopy(data[0])
                profile['binary_sha256'] = '0' * 64
                return profile, *data[1:]
            return data

        with patch.object(c87, 'parent', side_effect=changed):
            with self.assertRaisesRegex(GateError, 'profile differs: binary_sha256'):
                c87.analyze()


if __name__ == '__main__':
    unittest.main()
