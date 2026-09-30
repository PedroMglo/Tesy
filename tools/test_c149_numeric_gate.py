import math,struct,unittest
from c149_numeric_gate import payload,byte_entry,compare

class NativeGate(unittest.TestCase):
    def test_real_row_validation_and_negative_controls(self):
        row={'phase':'decode0','name':'ffn_moe_topk','ne':'4,1,1,1','nb':'4,16,16,16','bytes':'16','type':'i32'}
        payload(row,struct.pack('<4i',1,2,3,4))
        for data in (struct.pack('<4i',1,2,3,128),struct.pack('<4i',1,1,3,4),b'\0'*12):
            with self.assertRaises(ValueError):payload(row,data)
        f={'phase':'decode0','name':'ffn_moe_out','ne':'2880,1,1,1','nb':'4,11520,11520,11520','bytes':'11520','type':'f32'}
        payload(f,b'\0'*11520)
        with self.assertRaises(ValueError):payload(f,struct.pack('<f',math.nan)+b'\0'*11516)
    def test_native_canonical_offset_and_component_bytes(self):
        t={'blk.0.ffn_gate_exps.weight':{'n_bytes':128*64,'data_offset':4096}}
        row={'layer':'0','component':'0','expert':'2','offset':'4224','bytes':'64','buffer':'CPU','status':'PASS'}
        byte_entry(row,t)
        for k,v in [('expert','128'),('offset','4225'),('bytes','63'),('buffer','CUDA0'),('status','FAIL')]:
            with self.subTest(k=k),self.assertRaises(ValueError):byte_entry(dict(row,**{k:v}),t)
    def test_repeated_payload_bitwise_gate(self):
        a={'payload_sha256':{'decode0.logits.f32':'aaa'}}
        self.assertEqual(compare(a,a)['status'],'SAME_PROFILE_BITWISE_PASS')
        with self.assertRaises(ValueError):compare(a,{'payload_sha256':{'decode0.logits.f32':'bbb'}})
if __name__=='__main__':unittest.main()
