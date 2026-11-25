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

    def test_live_extent_and_final_charge(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            journal = root / "phase.pfj1"
            (root / "capture").write_bytes(b"123")
            with journal.open("wb") as f:
                journal.chmod(0o600)
                f.truncate(134217664)
                self.assertEqual(S["LiveOutput"].file_bytes(root), 3)
                f.truncate(1000)
                self.assertEqual(S["LiveOutput"].file_bytes(root), 1003)
                f.truncate(134217665)
                with self.assertRaises(ValueError):
                    S["LiveOutput"].file_bytes(root)

    def test_off_checks_absence_even_if_symlink_is_dangling(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d, "journal")
            self.assertEqual(S["inspect_journal"](file, False, {}, {}), {"enabled": False})
            file.symlink_to("absent")
            with self.assertRaises(ValueError):
                S["inspect_journal"](file, False, {}, {})


if __name__ == "__main__":
    unittest.main()
