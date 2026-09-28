"""Fresh-process comparison gate controls from preserved full captures."""
import unittest
from pathlib import Path

from c72_wave_repeat_gate import compare


FIRST = Path('results/c70-full-wave-boundary-20260928T1652Z/raw/c70-p12-wave-on01.capture')
OLD_FAIL = Path('results/c48-skip-boundary-20260928T0954Z/raw/c48-g2-on01.capture')


class C72WaveRepeatGate(unittest.TestCase):
    def test_valid_identity_and_distinct_old_capture(self):
        if not FIRST.is_dir() or not OLD_FAIL.is_dir():
            self.skipTest('local full-capture raw unavailable')
        self.assertEqual(compare(FIRST, FIRST)['status'], 'SAME_PROFILE_BITWISE_PASS')
        self.assertEqual(compare(FIRST, OLD_FAIL)['status'], 'FAIL_SAME_PROFILE_FIDELITY')


if __name__ == '__main__':
    unittest.main()
