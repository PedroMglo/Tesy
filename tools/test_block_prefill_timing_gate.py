import copy
import unittest
from block_prefill_timing_gate import validate,paired

def arm(profile,first,decode):
    state={'pending_queue':0,'n_calls':100,'layers':[dict(layer=i,slot_expert=list(range(40)),slot_state=[2]*40,slot_claimed=[False]*40,slot_generation=[1]*40) for i in range(36)]}
    final=copy.deepcopy(state)
    for layer in final['layers']:layer['slot_generation'][0]+=2 if profile=='A' else 1
    return dict(status='COMPLETE_CONTROLLED_WARM153_NATIVE_SERVICE',profile=profile,official_input_ids=[1]*2197,teacher_forced_ids=[2]*32,native_argmax_ids=[3]*33,external_prefill_calls=[256]*7+[252,153],decode_calls=32,decode_positions=[2197,2228],output_rows=33,FFN_last_layer_rows_per_call=1,layerspan=32 if profile=='A' else 153,numerical_FFN_tiles=[32,32,32,32,25],prefix2044_s=60,prefill153_s=first,decode32_s=decode,total_s=first+decode,initial=state,final=final)

class Gates(unittest.TestCase):
    def test_complete_accounting_and_invalid_counterproofs(self):
        fixture={'ids':[1]*2197,'continuation_ids':[2]*32};v=arm('A',10,8);validate(v,fixture,'A')
        for field,bad in [('official_input_ids',[]),('native_argmax_ids',[]),('decode_calls',31),('profile','B'),('total_s',1),('prefill153_s',float('nan')),('decode32_s',0)]:
            x=copy.deepcopy(v);x[field]=bad
            with self.assertRaises(ValueError,msg=field):validate(x,fixture,'A')

    def test_paired_gains_and_decode_protection(self):
        rows=[arm('A',10,8),arm('B',8,8),arm('B',8,8),arm('A',12,8)]
        out=paired(rows);self.assertAlmostEqual(out['median_paired_gain_percent']['prefill153_s'],(20+100/3)/2)
        self.assertEqual(out['status'],'GO_CONTROLLED_WARM153_NATIVE_COST')
        rows[1]['decode32_s']=10;rows[1]['total_s']=18
        self.assertEqual(paired(rows)['status'],'NO_GO_CONTROLLED_WARM153_NATIVE_COST')
        with self.assertRaises(ValueError):paired(rows[:3])
        rows[2]['initial']['layers'][0]['slot_generation'][0]+=1
        with self.assertRaises(ValueError):paired(rows)

if __name__=='__main__':unittest.main()
