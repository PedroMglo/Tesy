import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "interturn_screen", Path(__file__).with_name("screen.py")
)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
MARGIN = subject.MARGIN
SIZE = subject.SIZE
case = subject.case


class Cases(unittest.TestCase):
    def test_round_outwards_and_grant(self):
        d = case(Decimal("1.0000000008"), Decimal("1.0010000002"), 224, 199)
        self.assertEqual(d["upper_ns"], 1_000_001 + 2 * MARGIN)
        self.assertEqual(d["required_nvme_bytes"], 25 * SIZE)
        self.assertEqual(d["decision"], "NO_GO_FIXED_WINDOW")
        self.assertEqual(d["max_complete_keys"], 1)
        self.assertEqual(case(Decimal(1), Decimal(1), 167, 199)["decision"], "HEADROOM_ONLY")

    def test_overlap_and_fractional_key(self):
        with self.assertRaises(ValueError):
            case(Decimal(2), Decimal(1), 1, 0)
        self.assertEqual(case(Decimal(1), Decimal("1.000937599"), 1, 0)["max_complete_keys"], 0)
        self.assertEqual(case(Decimal(1), Decimal("1.000937600"), 1, 0)["max_complete_keys"], 1)


if __name__ == "__main__":
    unittest.main()
