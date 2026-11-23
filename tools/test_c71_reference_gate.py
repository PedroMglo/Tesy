"""C71 canonical receipt discriminants using historical resident rows."""
import copy
from pathlib import Path
import unittest

from c2_gate import GateError, strict_json
from c71_wave_reference_run import validate_result


RAW = Path('results/c7b-20260927T1206Z/raw')


class C71ReferenceGate(unittest.TestCase):
    def test_valid_cpu_gpu_and_masked_rows(self):
        for layer in (24, 25, 35):
            path = RAW / f'c7b-ref-p12-l{layer:02d}-01.stdout'
            if not path.is_file():
                self.skipTest('historical reference raw unavailable')
            self.assertTrue(validate_result(strict_json(path.read_text()), layer))

    def test_active_mismatch_and_wrong_placement_fail(self):
        path = RAW / 'c7b-ref-p12-l25-01.stdout'
        if not path.is_file():
            self.skipTest('historical reference raw unavailable')
        valid = strict_json(path.read_text())
        wrong_bits = copy.deepcopy(valid)
        wrong_bits['rows'][0]['ffn_bitwise'] = False
        self.assertFalse(validate_result(wrong_bits, 25))
        wrong_device = copy.deepcopy(valid)
        wrong_device['device'] = 'cpu'
        with self.assertRaisesRegex(GateError, 'schema/placement'):
            validate_result(wrong_device, 25)
