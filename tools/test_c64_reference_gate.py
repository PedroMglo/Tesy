"""Historical resident-layer control and one wrong active FFN bit."""
import json
from pathlib import Path
import unittest

from c64_p14_reference_run import validate_result


SOURCE=Path('results/c7b-20260927T1206Z/raw/c7b-ref-p12-l25-01.stdout')


class C64ReferenceGate(unittest.TestCase):
    def test_historical_canonical_positive_and_mutant(self):
        result=json.loads(SOURCE.read_text())
        self.assertTrue(result['all_bitwise'])
        result['schema']='c63-p14-layer-reference-v1'
        self.assertTrue(validate_result(result,25))  # GPU layer in both placements
        result['rows'][0]['ffn_bitwise']=False
        self.assertFalse(validate_result(result,25))
