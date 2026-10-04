import json
from pathlib import Path
import struct
import tempfile
import unittest
from block_grid_gate import inspect

class ActualGridEvidence(unittest.TestCase):
    def test_complete_rows_and_counterproofs(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);fixture=root/'fixture.json'
            fixture.write_text(json.dumps({'test':{'ids':[9,8],'continuation_ids':[3,4]}}))
            data=struct.pack('<f',1.25)*(2*201088)
            (root/'production-base.logits.f32').write_bytes(data)
            for k in (1,2):(root/f'prefix-only-{k}.logits.f32').write_bytes(data)
            out={'status':'PASS_SELECTED_DRAFT_INDEPENDENT_GRID','case':'test','B':2,'mode':'grid','official_prefix_ids':[9,8], 'checks':[
                {'known_rows':1,'prefix_only_inputs':[3,0],'fixed_padding':0,'preceding_complete_rows_bitwise':True},
                {'known_rows':2,'prefix_only_inputs':[3,4],'fixed_padding':0,'preceding_complete_rows_bitwise':True}]}
            def write(x): (root/'result.json').write_text(json.dumps(x))
            write(out);self.assertEqual(inspect(root,2,fixture,'test')['query_positions'],2)
            for key,value in [('checks',[]),('official_prefix_ids',[1]),('case','wrong')]:
                bad={**out,key:value};write(bad)
                with self.assertRaises(ValueError):inspect(root,2,fixture,'test')
            write(out)
            (root/'prefix-only-1.logits.f32').write_bytes(data[:-4])
            with self.assertRaisesRegex(ValueError,'full rows'):inspect(root,2,fixture,'test')
            (root/'prefix-only-1.logits.f32').write_bytes(data)
            ref=root/'observer.f32';ref.write_bytes(data)
            self.assertTrue(inspect(root,2,fixture,'test',ref)['observer_bitwise'])
            ref.write_bytes(struct.pack('<f',2)+data[4:])
            with self.assertRaisesRegex(ValueError,'neutrality blocked'):inspect(root,2,fixture,'test',ref)
            nan=struct.pack('<f',float('nan'))+data[4:]
            (root/'production-base.logits.f32').write_bytes(nan)
            for k in (1,2):(root/f'prefix-only-{k}.logits.f32').write_bytes(nan)
            with self.assertRaisesRegex(ValueError,'nonfinite'):inspect(root,2,fixture,'test')

if __name__=='__main__':unittest.main()
