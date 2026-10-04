import copy
import unittest
import json
import tempfile
from pathlib import Path
from block_layer_reuse_gate import components,SELECTED,inspect,clean

class Coverage(unittest.TestCase):
    def test_bias_generation_and_union_counterproofs(self):
        rows=[dict(layer=l,wave=0,logical=5,slot=4,generation=2,component=k,
                   bytes=4406400 if k<3 else 11520) for l in SELECTED for k in range(6)]
        unions={l:{5} for l in SELECTED};self.assertEqual(components(rows,unions),30)
        for mutate in ('omitted','bias','stale','union'):
            r=copy.deepcopy(rows);u=copy.deepcopy(unions)
            if mutate=='omitted':r=r[:-6]
            if mutate=='bias':r[4]['component']=3
            if mutate=='stale':r[2]['generation']=0
            if mutate=='union':u[0]={6}
            with self.assertRaises(ValueError,msg=mutate):components(r,u)

    def test_empty_witness_is_not_pass(self):
        with self.assertRaises(ValueError):components([],{l:set() for l in SELECTED})

    def test_empty_or_duplicate_stages_cannot_qualify(self):
        fixture={'ids':[1]*2197,'continuation_ids':[2]*6}
        layers=[dict(layer=i,slot_generation=[1]*40,slot_state=[2]*40,slot_claimed=[False]*40,slot_expert=list(range(40))) for i in range(36)]
        receipt=dict(status='COMPLETE_NATIVE_LAYER_REUSE_FIDELITY',mode='r2-tile',input_ids=fixture['ids'],teacher_forced_ids=fixture['continuation_ids'],layer_span=153,ffn_tile=32,native_argmax_ids=[3]*7,initial={'pending_queue':0,'layers':layers},after_prefill={'pending_queue':0,'layers':layers})
        with tempfile.TemporaryDirectory() as d:
            for stages in ([],[{'layer':0,'stage':'ffn_moe_out'}]*216):
                receipt['stages']=stages
                (Path(d)/'result.json').write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError,'stages omitted/duplicated'):inspect(d,fixture,'r2-tile')

    def test_clean_is_not_an_empty_capture_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            for mode,enabled in [('r2-tile',False),('r2-reuse-clean',True)]:
                (Path(d)/'result.json').write_text(json.dumps(dict(status='COMPLETE_NATIVE_LAYER_REUSE_FIDELITY',mode=mode,capture_enabled=enabled,stages=[],witness=[],capture_bytes=0)))
                with self.assertRaisesRegex(ValueError,'explicit clean'):clean(d,{'ids':[1],'continuation_ids':[2]*6},Path(d)/'reference')

if __name__=='__main__':unittest.main()
