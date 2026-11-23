import unittest
from pathlib import Path
from unittest.mock import patch

from c2_gate import GateError
import c93_session_wave_8k_boundary as c93


ROOT = Path('results/c93-session-wave-8k-boundary-20260928T2049Z')


class C93FreezeTests(unittest.TestCase):
    def test_actual_snapshot_control(self):
        protocol = c93.frozen(ROOT)
        self.assertEqual(protocol['profile']['n_ctx'], 8192)
        self.assertEqual(protocol['binary_sha256'],
                         'df915e8ca3ac0f0a11235619de6eaa2e7e8319324beb044440cec76c4ca005e5')

    def test_changed_model_mtime_rejected(self):
        original = c93.file_identity(c93.MODEL)
        changed = dict(original, mtime_ns=original['mtime_ns'] + 1)
        with patch.object(c93, 'file_identity', return_value=changed):
            with self.assertRaisesRegex(GateError, 'model stat differs'):
                c93.frozen(ROOT)


if __name__ == '__main__':
    unittest.main()
