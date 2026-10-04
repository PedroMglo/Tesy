import copy
import subprocess
import unittest
from pathlib import Path
from block_eagle3_loop_gate import validate

class IntegratedBoundary(unittest.TestCase):
    def test_real_native_acceptance_selftest_before_weights(self):
        root=Path(__file__).resolve().parents[1]
        exe=root/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z/build/block-eagle3-loop'
        result=subprocess.run([str(exe),'--self-test'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS_MODEL_FREE_NATIVE_GRID_ACCEPTANCE',result.stdout)
        self.assertIn('"weights_loaded":false',result.stdout)
    def test_complete_AR_evidence_and_invalid_missing_counts_or_metrics(self):
        fixture={'ids':[1,2,3]};tokens=list(range(20,37))
        value={'status':'MEASURED_NATIVE_CONFIRMED_LOOP','mode':'ar','official_prefix_ids':fixture['ids'],'count_limit':16,
            'native_confirmed_ids':tokens,'initial_anchor':20,'decode_confirmed_excluding_anchor':16,'finish':'DIAGNOSTIC_CAP',
            'iterations':[{'B':1,'input':a,'confirmed':b} for a,b in zip(tokens,tokens[1:])],
            'target_verification_calls':16,'target_full_logit_rows':16,'wall_s':1.,'prefill_total_s':1.,
            'prefill_head_processing_s':0.,'draft_total_s':0.,'verification_head_processing_s':0.,'diagnostic_reference_s':0.}
        self.assertEqual(validate(value,fixture)['decode_confirmed_excluding_anchor'],16)
        for key,replacement in [('iterations',[]),('native_confirmed_ids',[]),('wall_s',float('nan')),('decode_confirmed_excluding_anchor',17),('target_full_logit_rows',1),('official_prefix_ids',[1])]:
            bad=copy.deepcopy(value);bad[key]=replacement
            with self.assertRaises(ValueError):validate(bad,fixture)

if __name__=='__main__':unittest.main()
