import unittest
from pathlib import Path
from unittest.mock import patch
import c141_analyze_slots44 as gate
import c141_slots44_server as family
from c2_gate import GateError

def pair(primary,protection=0,work=True):
    gains={k:0 for k in gate.previous.METRICS};gains['warm_decode_s']=primary;gains['cold_prefill_s']=protection
    return {'same_work':work,'gain_percent':gains}

class GateTest(unittest.TestCase):
    def test_screen_boundary(self):
        self.assertEqual(gate.paired_gate([pair(8,-5),pair(8,-5)],2)[0],'SCREEN_GO_UNIFORM44_NOMINAL153')
        self.assertEqual(gate.paired_gate([pair(8,-5.01),pair(8,-5.01)],2)[0],'NO_GO_UNIFORM44_NOMINAL153')
    def test_positive_median_does_not_hide_zero(self):
        self.assertEqual(gate.paired_gate([pair(20),pair(0)],2)[0],'NO_GO_UNIFORM44_NOMINAL153')
    def test_divergence(self):
        self.assertEqual(gate.paired_gate([pair(10),pair(10,work=False)],2)[0],'INCONCLUSIVE_OUTPUT_DIVERGENCE')
    def test_three_new_confirmation_pairs(self):
        self.assertEqual(gate.paired_gate([pair(8),pair(9),pair(10)],3)[0],'CONFIRMED_UNIFORM44_NOMINAL153')
        with self.assertRaises(GateError):gate.paired_gate([pair(10),pair(10)],3)
    def test_clock_budget_and_arms(self):
        root=Path('results/c141-uniform44-screen-20260929T2330Z').resolve();family.configure(root)
        self.assertEqual([s[1] for s in family.campaign.ORDER],['control','candidate','candidate','control'])
        self.assertEqual(family.campaign.CAP,20*2**30)
        with patch.object(family,'DEADLINE',family.datetime.fromisoformat('2026-09-29T01:00:00+00:00')):
            with self.assertRaises(GateError):family.budget(root,4)

if __name__=='__main__':unittest.main()
