import copy
import unittest
import json
import tempfile
import subprocess
import sys
from pathlib import Path
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

    def test_real_aggregate_entrypoint_writes_separate_analysis_without_weights(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);output=root/'reanalysis-v2';output.mkdir();runs=[]
            fixture=root/'fixture.json';fixture.write_text(json.dumps({c:{'ids':[101,102,103]} for c in CLASSES}))
            initial={'pending_queue':0,'n_calls':36,'n_miss':0,'n_preload':0,'stall_us':0,
                'layers':[{'layer':i,'slot_generation':[0]*40,'slot_state':[0]*40,'slot_claimed':[False]*40,
                    'slot_expert':[-1]*40,'native_cache_buffer':'CPU','logical_bytes_per_load':4} for i in range(36)]}
            for i,v in enumerate(self.rows()):
                native=root/f'arm{i}';native.mkdir();(native/'result.json').write_text(json.dumps(v))
                (native/'initial-residency.json').write_text(json.dumps(initial))
                final=copy.deepcopy(initial);final['n_calls']+=36*v['target_verification_calls']
                (native/'final-residency.json').write_text(json.dumps(final));runs.append({'command':['unused']*5+[str(native)]})
            (root/'protocol.json').write_text(json.dumps({'development_fixture':str(fixture),'runs':runs}))
            exe=Path(__file__).with_name('block_eagle3_development_gate.py')
            result=subprocess.run([sys.executable,str(exe),str(root),'--output-dir',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads((output/'development-screen.json').read_text())['decision'],'GO_DEVELOPMENT_REAL_UTILITY_SCREEN')
            self.assertFalse((root/'development-screen.json').exists())
            again=subprocess.run([sys.executable,str(exe),str(root),'--output-dir',str(output)],capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0)

if __name__=='__main__':unittest.main()
