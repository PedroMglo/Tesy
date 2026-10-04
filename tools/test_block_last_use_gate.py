import copy
import unittest
from block_last_use_gate import compare
from block_layer_reuse_gate import STAGES

class Fidelity(unittest.TestCase):
    def test_same_payload_and_initial_state_required(self):
        payloads={f'{layer}:{stage}':'a' for layer in range(36) for stage in STAGES}
        payloads.update({name:'a' for name in ['prefill.logits.f32',*[f'decode{i}.logits.f32' for i in range(6)]]})
        v=dict(status='PASS_NATIVE_R2_COMPLETE_LAYER_CAPTURE',stage_payloads=payloads,initial=dict(layers=['state'],pending_queue=0,n_calls=10),native_argmax_ids=[1]*7,consumer_components=6)
        self.assertEqual(compare(v,v)['status'],'PASS_SELECTED_AUTHORITATIVE_LAST_USE_FIDELITY')
        for field,bad in [('stage_payloads',{}),('initial',dict(layers=['other'],pending_queue=0,n_calls=10)),('native_argmax_ids',[2]*7)]:
            other=copy.deepcopy(v);other[field]=bad
            with self.assertRaises(ValueError):compare(other,v)
        missing=copy.deepcopy(v);missing['stage_payloads']={}
        with self.assertRaises(ValueError):compare(missing,missing)

if __name__=='__main__':unittest.main()
