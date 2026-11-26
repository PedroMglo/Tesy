"""Contract of the optional C270 environment on the original gate."""

import sys
import unittest
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GATE))
import prepare  # noqa: E402


class GateEnvironment(unittest.TestCase):
    def test_original_environment_and_explicit_child(self):
        self.assertEqual(prepare.ldd_environment(), {"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        self.assertEqual(prepare.ldd_environment("/a:/b")["LD_LIBRARY_PATH"], "/a:/b")
        for v in ("", ":/a", "/a:", "relative", "/a::/b"):
            with self.assertRaises(ValueError):
                prepare.ldd_environment(v)
