"""Prospective C124 three-pair policy controls."""

import unittest

from c2_gate import GateError
from c124_analyze import confirmation_gate
from c124_nominal_confirm import epoch_budget


def pair(primary=10, cold_prefill=0):
    return {'gain_percent':{'warm_first_final_s':primary,'warm_decode_s':0,
                            'cold_decode_s':0,'cold_first_final_s':0,
                            'cold_prefill_s':cold_prefill,'warm_prefill_s':0}}


class C124GateTest(unittest.TestCase):
    def test_three_pairs_and_protections(self):
        self.assertTrue(confirmation_gate([pair(),pair(),pair()])[0])
        self.assertFalse(confirmation_gate([pair(0),pair(),pair()])[0])
        self.assertFalse(confirmation_gate([pair(cold_prefill=-6)]*3)[0])
        with self.assertRaises(GateError):
            confirmation_gate([pair(),pair()])

    def test_existing_epoch_cost_is_not_reset(self):
        from pathlib import Path
        row=epoch_budget(Path('/tmp/tesy-c124-test-no-run'),6)
        self.assertGreater(row['measured_live_intervals_s'],1200)
        self.assertEqual(row['unreceipted_live_allowance_s'],1200)
        self.assertEqual(row['worst_case_s'],4560)


if __name__=='__main__':
    unittest.main()
