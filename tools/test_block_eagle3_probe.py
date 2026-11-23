import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from block_eagle3_probe_gate import validate

class HeadProbe(unittest.TestCase):
    def test_native_bad_fixture_rejected_before_model_or_root(self):
        repo=Path(__file__).resolve().parents[1]
        exe=repo/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z/build/block-eagle3-probe'
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);f=d/'fixture.json';f.write_text(json.dumps({'bad':{'ids':[],'continuation_ids':[]}}))
            r=subprocess.run([str(exe),'/missing-target.gguf','/missing-head.gguf',str(f),'bad',str(d/'raw'),'v1'],capture_output=True,text=True)
            self.assertEqual(r.returncode,1);self.assertIn('selected head boundary differs from freeze',r.stderr);self.assertFalse((d/'raw').exists())
    def test_acceptance_first_middle_last_bonus_and_anchor_not_double_counted(self):
        for accepted in range(8):
            ids=list(range(10,17));winners=ids.copy()+[25]
            if accepted<7:winners[accepted]=99
            v={'status':'PASS_SELECTED_HEAD_BOUNDARY','B':8,'K':7,'head_ngl':1,'head_target_layers':[2,18,33],'official_prefix_ids':[1],
                'target_profile':'C75/P12/slots40/ub32/ctx8192/GOMPunset','native_proposed_ids':ids,'target_native_argmax':winners,'accepted_draft_count':accepted,
                'new_confirmable_tokens':accepted+1,'correction_or_bonus':winners[accepted],'anchor_known_input':7,
                'draft_seven_s':.1,'verification_head_processing_s':.1,'prefill_head_processing_s':.1,'prefill_total_s':.3,'verify_plus_head_process_s':.3,
                'R1_causal_checks':[{'known':k,'prefix_only_inputs':([7]+ids)[:k]+[0]*(8-k),'preceding_rows_bitwise':True} for k in range(1,9)]}
            self.assertEqual(validate(v,{'ids':[1]})['L'],accepted+1)
            for bad in ({**v,'new_confirmable_tokens':accepted+2},{**v,'native_proposed_ids':[]},{**v,'draft_seven_s':float('nan')},{**v,'R1_causal_checks':[]}):
                with self.assertRaises(ValueError):validate(bad,{'ids':[1]})

if __name__=='__main__':unittest.main()
