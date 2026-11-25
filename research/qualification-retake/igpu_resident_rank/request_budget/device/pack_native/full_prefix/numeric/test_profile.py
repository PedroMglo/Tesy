import sys
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
S = run_path(str(HERE / "profile.py"))


class NumericTest(unittest.TestCase):
    def test_limit_is_only_the_new_file_capacity(self):
        values = ["scope", "LimitFSIZE=8388608", "MemorySwapMax=0"]
        S["Scope"].replace_once(values, "LimitFSIZE=8388608", "LimitFSIZE=33554432")
        self.assertEqual(values, ["scope", "LimitFSIZE=134217728", "MemorySwapMax=0"])
        with self.assertRaises(ValueError):
            S["Scope"].replace_once(values, "MemorySwapMax=0", "MemorySwapMax=100")

    def test_off_checks_absence_even_if_symlink_is_dangling(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d, "journal")
            self.assertEqual(S["inspect_journal"](file, False, {}, {}), {"enabled": False})
            file.symlink_to("absent")
            with self.assertRaises(ValueError):
                S["inspect_journal"](file, False, {}, {})


if __name__ == "__main__":
    unittest.main()
