import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from epoch_accounting import Epoch


class ActiveWall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.e = Epoch.__new__(Epoch)
        self.e.path = self.path
        self.e.boot_id = 'new-boot'
        self.rows = [dict(boot_id='old-boot', start_monotonic_s=100,
                         end_monotonic_s=140),
                     dict(boot_id='new-boot', start_monotonic_s=5,
                         end_monotonic_s=15)]
        self.session = dict(boot_id='new-boot', start_monotonic_s=20)

    def measured(self):
        (self.path / 'active-wall.jsonl').write_text(
            ''.join(json.dumps(r) + '\n' for r in self.rows))
        (self.path / 'active-session.json').write_text(json.dumps(self.session))
        with patch('epoch_accounting.time.monotonic', return_value=30):
            return self.e.active_wall()

    def test_distinct_boots_and_idle_gap(self):
        self.assertEqual(self.measured(), 60)

    def test_cross_reboot_open_session_requires_reconciliation(self):
        self.session['boot_id'] = 'old-boot'
        with self.assertRaisesRegex(ValueError, 'reboot'):
            self.measured()

    def test_overlap_cannot_gain_credit(self):
        self.session['start_monotonic_s'] = 10
        with self.assertRaises(ValueError):
            self.measured()

    def test_nonfinite_and_negative_spans_fail(self):
        for value in (float('nan'), float('inf'), 99):
            self.rows[0]['end_monotonic_s'] = value
            with self.assertRaises(ValueError):
                self.measured()

    def test_closed_session_does_not_charge_idle(self):
        self.session = None
        self.assertEqual(self.measured(), 50)

    def test_unknown_endpoint_preparation_receives_no_overlap_credit(self):
        self.e.config={'preopen_wall_conservative_charge_s':17.5}
        self.assertEqual(self.measured(),77.5)
        for value in (-1,float('nan'),True):
            self.e.config['preopen_wall_conservative_charge_s']=value
            with self.assertRaises(ValueError):self.measured()


if __name__ == '__main__':
    unittest.main()
