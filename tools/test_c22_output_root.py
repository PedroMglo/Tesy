import tempfile
from pathlib import Path
import unittest

from c2_gate import GateError
from c22_prefix_pairs import require_output_root


class OutputRootTest(unittest.TestCase):
    def test_missing_server_output_root_is_rejected_before_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(GateError, 'output directory missing'):
                require_output_root(root)
            (root / 'raw').mkdir()
            self.assertEqual(require_output_root(root), root / 'raw')
