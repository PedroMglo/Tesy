"""Full-capture schema and preserved historical mismatch as a negative control."""
import unittest
from pathlib import Path

from c70_full_boundary_gate import compare, inspect


ROOT = Path('results')
OFF = ROOT / 'c47-skip-boundary-20260928T0927Z/raw/c47-g2-off01.capture'
ON = ROOT / 'c48-skip-boundary-20260928T0954Z/raw/c48-g2-on01.capture'


class C70FullBoundaryGate(unittest.TestCase):
    def test_full_historical_captures_parse_and_old_fail_survives(self):
        if not OFF.is_dir() or not ON.is_dir():
            self.skipTest('local historical raw unavailable')
        off = inspect(OFF, skip_on=False)
        on = inspect(ON, skip_on=True)
        self.assertEqual(len(off['core']), 1500)
        self.assertEqual(len(on['core']), 1500)
        self.assertEqual(off['sentinels'], 0)
        self.assertGreater(on['sentinels'], 0)
        result = compare(OFF, ON)
        self.assertEqual(result['status'], 'FAIL_SAME_PROFILE_FIDELITY')
        self.assertTrue(result['mismatch'])


if __name__ == '__main__':
    unittest.main()
