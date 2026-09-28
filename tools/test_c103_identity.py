import unittest
from unittest.mock import patch

from c2_gate import GateError
import c103_server_wave_toggle as c103


class MeasurementCommitIdentity(unittest.TestCase):
    def test_full_sha_passes_clean_environment(self):
        full = 'a' * 40
        with patch.object(c103.base, 'git', side_effect=[full, '']), \
             patch.object(c103, 'relevant_environment', return_value={}):
            c103.preflight_identity(full)

    def test_abbreviated_sha_is_rejected_before_git_or_model(self):
        with patch.object(c103.base, 'git') as git:
            with self.assertRaisesRegex(GateError, 'full 40-character SHA'):
                c103.preflight_identity('8201488')
            git.assert_not_called()

    def test_dirty_full_sha_is_rejected(self):
        full = 'b' * 40
        with patch.object(c103.base, 'git', side_effect=[full, ' M tools/example.py']), \
             patch.object(c103, 'relevant_environment', return_value={}):
            with self.assertRaisesRegex(GateError, 'worktree'):
                c103.preflight_identity(full)


if __name__ == '__main__':
    unittest.main()
