"""Physical-time totals include server receipts and reject broken run rows."""

import json
import os
from pathlib import Path
import tempfile
import unittest

from c2_gate import GateError
from c8_observer_runner import program_physical_consumed


class BudgetAccountingTests(unittest.TestCase):
    def test_both_run_formats_and_negative(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                raw = Path('results/c9-test/raw')
                raw.mkdir(parents=True)
                (raw / 'c9-api.json').write_text(json.dumps(
                    {'preflight': {'run_id': 'c9-api'}, 'elapsed_s': 4.25}))
                (raw / 'c9-probe.json').write_text(json.dumps(
                    {'run_id': 'c9-probe', 'elapsed_s': 3.5}))
                (raw / 'c9-api.preflight.json').write_text(json.dumps(
                    {'run_id': 'c9-api'}))
                self.assertEqual(program_physical_consumed(), 7.75)
                (raw / 'c9-probe.json').write_text(json.dumps(
                    {'run_id': 'c9-probe', 'elapsed_s': -3.5}))
                with self.assertRaisesRegex(GateError, 'physical-time receipt'):
                    program_physical_consumed()
            finally:
                os.chdir(original)


if __name__ == '__main__':
    unittest.main()
