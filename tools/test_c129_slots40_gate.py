import unittest

from c128_slots40_analyze import METRICS
from c129_slots40_analyze import confirm_gate


def row(primary, *, cold_prefill=0, same_work=True):
    gains = {metric:0.0 for metric in METRICS}
    gains['warm_decode_s']=primary
    gains['cold_prefill_s']=cold_prefill
    return {'same_work':same_work,'gain_percent':gains}


class TestC129Gate(unittest.TestCase):
    def test_three_fresh_positive_pairs(self):
        status, medians = confirm_gate([row(8),row(10),row(9)])
        self.assertEqual(status,'CONFIRMED_SLOTS40_NOMINAL153')
        self.assertEqual(medians['warm_decode_s'],9)

    def test_single_negative_primary_blocks(self):
        self.assertEqual(confirm_gate([row(14),row(11),row(-1)])[0],
                         'NO_GO_CONFIRM_SLOTS40_NOMINAL153')

    def test_cold_prefill_protection_blocks(self):
        self.assertEqual(confirm_gate([row(12,cold_prefill=-6),row(12,cold_prefill=-6),row(12)])[0],
                         'NO_GO_CONFIRM_SLOTS40_NOMINAL153')

    def test_output_divergence_not_causal_timing(self):
        self.assertEqual(confirm_gate([row(12),row(12),row(12,same_work=False)])[0],
                         'INCONCLUSIVE_OUTPUT_DIVERGENCE')


if __name__=='__main__':
    unittest.main()
