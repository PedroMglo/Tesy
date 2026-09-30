import csv,json,struct,tempfile,unittest
from pathlib import Path
import c7_boundary_gate as g
from c2_gate import GateError
from native64_prepare import capture_source,reference_source

class Native64Contract(unittest.TestCase):
    def test_native_schedule_positions_masks_and_legacy(self):
        phases,masks=g.phase_contract(64)
        self.assertEqual(phases[:3],('prefill0','prefill64','prefill_final'))
        self.assertEqual([g.state_metadata(p,0,ubatch=64) for p in phases[:3]],[(0,0,64),(1,64,64),(2,128,61)])
        self.assertEqual(g.state_metadata('prefill_final',35,ubatch=64),(2,188,1))
        self.assertEqual([(m['chunk'],m['first_abs']) for m in masks],[('0','0'),('1','64')])
        self.assertEqual(g.state_metadata('prefill_final',0),(5,160,29))
        for phase in ('prefill128','prefill32','decode2'):
            with self.assertRaises(GateError):g.state_metadata(phase,0,ubatch=64)
        with self.assertRaises(GateError):g.phase_contract(96)
    def test_generation_preserves_arithmetic_and_full_capture(self):
        original=Path('tools/c127_slots40_boundary_capture.cpp').read_text();new=capture_source(original)
        self.assertIn('cp.n_ubatch = 64;',new);self.assertIn('mp.moe_stream_slots = 40;',new)
        self.assertIn('i == 0 || i == 1 || i == 7 || i == 31',new)
        self.assertNotIn('prefill128',new);self.assertIn('chunk*64',new)
        before=original[original.index('void verify_slots'):original.index('int main')]
        self.assertEqual(before[:before.index('bool capture') if 'bool capture' in before else before.index('state.prefill &&')-100],new[new.index('void verify_slots'):new.index('int main')][:before.index('bool capture') if 'bool capture' in before else before.index('state.prefill &&')-100])
        ref=reference_source(Path('tools/c7_layer_reference.cpp').read_text())
        self.assertIn('phase == "prefill64" ? 64',ref);self.assertIn('(layer == 35 ? 1 : 61)',ref)
        with self.assertRaises(ValueError):capture_source(original.replace('cp.n_ubatch = 32;','cp.n_ubatch = 16;'))
    def test_incomplete_or_wrong_native64_capture_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);phases,masks=g.phase_contract(64)
            (root/'phases.txt').write_text('\n'.join(phases)+'\n')
            with (root/'masked.tsv').open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(masks[0]),delimiter='\t');w.writeheader();w.writerows(masks)
            row=dict(zip(g.INDEX_FIELDS,('prefill0','0','0','0','64','ffn_moe_topk','i32','4,64,1,1','4,16,1024,1024','1024','prefill0_0_ffn_moe_topk_0.bin')))
            (root/row['file']).write_bytes(b'\0'*1024)
            def index():
                with (root/'index.tsv').open('w') as f:
                    w=csv.DictWriter(f,fieldnames=g.INDEX_FIELDS,delimiter='\t');w.writeheader();w.writerow(row)
            index()
            with self.assertRaisesRegex(GateError,'incomplete'):g.capture(root,ubatch=64)
            for key,value in [('state_tokens','32'),('first_abs','64'),('chunk','1'),('bytes','1020'),('ne','4,32,1,1')]:
                saved=row[key];row[key]=value;index()
                with self.assertRaisesRegex(GateError,'invalid'):g.capture(root,ubatch=64)
                row[key]=saved
            index();(root/row['file']).write_bytes(struct.pack('<i',-1)+b'\0'*1020)
            with self.assertRaisesRegex(GateError,'negative'):g.capture(root,ubatch=64)
            row['name']='attn_post_norm';row['type']='f32';row['ne']='2880,64,1,1';row['nb']='4,11520,737280,737280';row['bytes']='737280';row['file']='prefill0_0_attn_post_norm_0.bin'
            (root/row['file']).write_bytes(struct.pack('<f',float('nan'))+b'\0'*(737280-4));index()
            with self.assertRaisesRegex(GateError,'nonfinite'):g.capture(root,ubatch=64)
