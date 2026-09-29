import unittest

from c2_gate import GateError
from c128_slots40_analyze import METRICS, screen_gate


def pair(primary, *, cold_prefill=0, same_work=True):
    gains = {key:0.0 for key in METRICS}
    gains['warm_decode_s'] = primary
    gains['cold_prefill_s'] = cold_prefill
    return {'same_work':same_work, 'gain_percent':gains}


class TestC128ScreenGate(unittest.TestCase):
    def test_positive_equal_work(self):
        status, medians = screen_gate([pair(8),pair(10)])
        self.assertEqual(status,'SCREEN_GO_SLOTS40_NOMINAL153')
        self.assertEqual(medians['warm_decode_s'],9)

    def test_protected_cold_prefill_blocks_good_primary(self):
        status, _ = screen_gate([pair(12,cold_prefill=-6),pair(11,cold_prefill=-6)])
        self.assertEqual(status,'NO_GO_SLOTS40_NOMINAL153')

    def test_nonpositive_pair_blocks_positive_median(self):
        status, _ = screen_gate([pair(18),pair(0)])
        self.assertEqual(status,'NO_GO_SLOTS40_NOMINAL153')

    def test_divergent_work_is_inconclusive(self):
        status, _ = screen_gate([pair(10),pair(11,same_work=False)])
        self.assertEqual(status,'INCONCLUSIVE_OUTPUT_DIVERGENCE')

    def test_incomplete_metrics_rejected(self):
        bad = pair(9)
        del bad['gain_percent']['warm_prefill_s']
        with self.assertRaises(GateError):
            screen_gate([bad,pair(9)])


if __name__ == '__main__':
    unittest.main()
