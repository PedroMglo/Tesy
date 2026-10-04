import copy
import unittest
from block_eagle3_development_gate import evaluate,CLASSES

class DevelopmentScreen(unittest.TestCase):
    def rows(self):
        rows=[];tokens=list(range(20,53))
        for case in CLASSES:
            for mode,t in [('ar',10.),('head-measure',8.),('head-measure',7.),('ar',9.)]:
                steps=[{'B':1,'input':a,'confirmed':b} for a,b in zip(tokens,tokens[1:])]
                if mode=='head-measure':
                    steps=[]
                    for n in range(4):
                        steps.append({'B':8,'grid_start':3+8*n,'known_rows':1,'target_inputs':tokens[n*8:n*8+8],
                            'native_proposals':tokens[n*8+1:n*8+8],'target_argmax':tokens[n*8+1:n*8+9],
                            'new_confirmed':tokens[n*8+1:n*8+9],'accepted_draft_count':7,'feature_row':7,
                            'diagnostic_pattern':'REAL_HEAD_UNMODIFIED','clean_R1_checked_rows':0})
                rows.append({'status':'MEASURED_NATIVE_CONFIRMED_LOOP','case':case,'mode':mode,'count_limit':32,
                    'official_prefix_ids':[101,102,103],'initial_anchor':20,'finish':'DIAGNOSTIC_CAP',
                    'decode_confirmed_excluding_anchor':32,'wall_s':t,'prefill_total_s':1.,'native_confirmed_ids':tokens,
                    'iterations':steps,'target_verification_calls':len(steps),'target_full_logit_rows':32,
                    'draft_total_s':.01 if mode!='ar' else 0.,'verification_head_processing_s':.01 if mode!='ar' else 0.,
                    'diagnostic_reference_s':0.,'prefill_head_processing_s':0.})
        return rows
    def test_paired_ratios_and_both_classes_required(self):
        rows=self.rows();r=evaluate(rows)
        self.assertEqual(r['decision'],'GO_DEVELOPMENT_REAL_UTILITY_SCREEN')
        self.assertAlmostEqual(r['classes'][0]['median_decode_gain_percent'],(20+100*2/9)/2)
        rows[5]['wall_s']=12.
        self.assertEqual(evaluate(rows)['decision'],'NO_GO_CURRENT_HEAD_GRID_DEVELOPMENT_SCREEN')
    def test_missing_arms_wrong_order_nan_or_early_eos_never_gain_zero(self):
        with self.assertRaises(ValueError):evaluate(self.rows()[:-1])
        bad=self.rows();bad[0]['mode']='head-measure'
        with self.assertRaises(ValueError):evaluate(bad)
        bad=self.rows();bad[1]['wall_s']=float('nan')
        with self.assertRaises(ValueError):evaluate(bad)
        bad=self.rows();bad[1]['decode_confirmed_excluding_anchor']=3
        bad[1]['finish']='EOS';bad[1]['native_confirmed_ids']=[20,21,22,23];bad[1]['iterations']=bad[1]['iterations'][:1]
        step=bad[1]['iterations'][0];step['new_confirmed']=[21,22,23];step['accepted_draft_count']=3;step['feature_row']=2
        bad[1]['target_verification_calls']=1;bad[1]['target_full_logit_rows']=8
        r=evaluate(bad);self.assertIsNone(r['classes'][0]['pairs'][0]['gain_percent']);self.assertEqual(r['decision'],'NO_GO_CURRENT_HEAD_GRID_DEVELOPMENT_SCREEN')

if __name__=='__main__':unittest.main()
