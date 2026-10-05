import copy
import unittest
from test_block_prefill_timing_gate import arm as old_arm
from r2_causal_gate import validate, evaluate, validate_runs

def arm(profile,case,pre=8,decode=8):
    n=2197 if case=='nominal153' else 2105
    v=old_arm('A',pre,decode);v.update(status='COMPLETE_NATIVE_R2_CAUSAL_WORK',profile=profile,case=case,mode={'R0':0,'T':1,'E':2}[profile],official_input_ids=[1]*n,decode_positions=[n,n+31],layerspan=32 if profile=='R0' else 153,last_use_order_env=None if profile=='R0' else '1',initial_prefix_mode=0,vocab=201088,full_row_retention_bytes=33*201088*4,prefix_s=60)
    v.pop('prefix2044_s');v['external_prefill_calls']=[256]*7+[n-153-1792,153]
    return v

def cases(t=8,e=8):
    return {c:[arm(p,c,10 if p=='R0' else t if p=='T' else e) for p in ('R0','T','E','E','T','R0')] for c in ('nominal153','code153')}

class Gates(unittest.TestCase):
    def test_missing_start_inventory_reproduces_c277_before_collect(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from run_bounded import inventory_before_spawn
        root=Path(__file__).resolve().parents[1]
        protocol=json.loads((root/'results/c277-r2-new-input-fidelity-20261005/protocol.json').read_text())
        with patch('c118_start_inventory.collect') as collect:
            with self.assertRaisesRegex(RuntimeError,'opt-in frozen inventory contract invalid'):
                inventory_before_spawn(root,'model-free-c277-counterproof',protocol)
            collect.assert_not_called()
    def test_input_mode_rows_clocks_counterproofs(self):
        for c in ('nominal153','code153'):
            v=arm('T',c);f={'ids':v['official_input_ids'],'continuation_ids':[2]*32};validate(v,f,'T',c)
            for k,bad in [('official_input_ids',[]),('mode',2),('decode_positions',[1,32]),('native_argmax_ids',[]),('prefill153_s',float('nan')),('decode32_s',0),('total_s',1),('output_rows',1),('initial_prefix_mode',1)]:
                x=copy.deepcopy(v);x[k]=bad
                with self.assertRaises(ValueError,msg=k):validate(x,f,'T',c)
    def test_choose_simple_tile_unless_shared_pays_coordination(self):
        self.assertEqual(evaluate(cases())['selected'],'T')
        self.assertEqual(evaluate(cases(e=7))['selected'],'E')
        self.assertIsNone(evaluate(cases(t=10,e=10))['selected'])
        self.assertEqual(evaluate(cases(t=10,e=8))['selected'],'E')
    def test_both_cases_and_initial_state_required(self):
        x=cases();x['code153'][1]['prefill153_s']=10;x['code153'][1]['total_s']=18
        x['code153'][4]['prefill153_s']=10;x['code153'][4]['total_s']=18
        self.assertEqual(evaluate(x)['selected'],'E')
        with self.assertRaises(ValueError):evaluate({'nominal153':cases()['nominal153']})
        x=cases();x['code153'][2]['initial']['layers'][0]['slot_generation'][0]+=1
        with self.assertRaises(ValueError):evaluate(x)
        x=cases();x['code153'].pop()
        with self.assertRaises(ValueError):evaluate(x)
    def test_decode_regression_not_compensated_by_prefill(self):
        x=cases(e=6)
        for c in x:
            for v in x[c]:
                if v['profile']=='E':v['decode32_s']=10;v['total_s']=16
        self.assertEqual(evaluate(x)['selected'],'T')
    def test_runs_cannot_reuse_roots_or_ids_or_reorder(self):
        runs=[dict(id=str(i),profile=p,command=['bin','model','fixture',c,'/tmp/test-r2-'+str(i),p,'v1']) for i,(c,p) in enumerate((c,p) for c in ('nominal153','code153') for p in ('R0','T','E','E','T','R0'))]
        validate_runs(runs)
        for field in ('id','path'):
            x=copy.deepcopy(runs)
            if field=='id':x[1]['id']=x[0]['id']
            else:x[1]['command'][4]=x[0]['command'][4]
            with self.assertRaises(ValueError):validate_runs(x)
        with self.assertRaises(ValueError):validate_runs(runs[:-1])
        with self.assertRaises(ValueError):validate_runs(list(reversed(runs)))

if __name__=='__main__':unittest.main()
