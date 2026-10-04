import copy
import unittest
from block_amortization_gate import evaluate

class PairedMargin(unittest.TestCase):
    def cases(self):
        rows=[]
        for case in ['development-code-rle','development-structured-route','anchor-nominal153']:
            arms=[]
            for mode,wall in [('ar',10),('block',8),('block',4),('ar',5)]:arms.append(dict(mode=mode,wall_s=wall,initial={'layers':'same'},case=case,contrast_B=2,native_argmax_ids=list(range(32))))
            rows.append({'case':case,'arms':arms})
        return rows
    def test_percent_per_pair_and_full_budget_counts(self):
        result=evaluate(self.cases(),2);self.assertEqual(result['status'],'GO_A1_COMPLETE_BLOCK_AMORTIZATION')
        self.assertEqual(result['classes'][0]['median_paired_gain_percent'],20)
        self.assertEqual(result['classes'][0]['pairs'][0]['margins_L1_to_B'][-1]['positions'],2)
        self.assertLess(result['classes'][0]['pairs'][0]['margins_L1_to_B'][0]['D_budget_s'],0)
    def test_missing_profiles_state_and_nonfinite_are_not_gain_zero(self):
        for change in ('omit','profile','state','nan','zero'):
            rows=self.cases()
            if change=='omit':rows[0]['arms'].pop()
            if change=='profile':rows[0]['arms'][1]['mode']='ar'
            if change=='state':rows[0]['arms'][1]['initial']={'layers':'different'}
            if change=='nan':rows[0]['arms'][1]['wall_s']=float('nan')
            if change=='zero':rows[0]['arms'][1]['wall_s']=0
            with self.assertRaises(ValueError):evaluate(rows,2)
    def test_unfavorable_outputs_retained_and_ratio_of_medians_not_used(self):
        rows=self.cases();rows[0]['arms'][0]['wall_s']=10;rows[0]['arms'][1]['wall_s']=5;rows[0]['arms'][3]['wall_s']=100;rows[0]['arms'][2]['wall_s']=90
        result=evaluate(rows,2);self.assertEqual(result['classes'][0]['median_paired_gain_percent'],30)
        rows[0]['arms'][2]['wall_s']=110
        result=evaluate(rows,2);self.assertFalse(result['classes'][0]['economic_class_GO'])
        self.assertEqual(len(result['classes'][0]['pairs']),2)

if __name__=='__main__':unittest.main()
