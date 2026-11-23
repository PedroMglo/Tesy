import json
from pathlib import Path
import struct
import tempfile
import unittest
from block_continuity_gate import inspect

class ContinuityEvidence(unittest.TestCase):
    def test_actual_payloads_cardinality_identity_cancel_and_draft_counterproof(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);fixture=p/'fixture';spec={'ids':[8,9],'continuation_ids':[1,2,3,4,5,6]};fixture.write_text(json.dumps({'x':spec}))
            data=struct.pack('<f',2.5)*(2*201088)
            checks=[]
            for g in range(3):
                (p/f'grid-{g}.base.f32').write_bytes(data)
                for k in (1,2):
                    (p/f'grid-{g}.known-{k}.f32').write_bytes(data)
                    checks.append({'grid':g,'known':k,'position':2+2*g,'inputs':spec['continuation_ids'][2*g:2*g+k]+[0]*(2-k),'fixed_padding':0,'complete_preceding_rows_bitwise':True})
            out={'status':'PASS_SELECTED_MULTIGRID_R1_AND_NATIVE_CANCEL','case':'x','B':2,'official_prefix_ids':[8,9],'native_continuation_ids':spec['continuation_ids'],'checks':checks,'abort_rc':2,'abort_callback_calls':1,'cancel_then_clean_full_logits_bitwise':True,'scope':'fixture'}
            def write(x):(p/'result.json').write_text(json.dumps(x))
            write(out);self.assertEqual(inspect(p,fixture,'x',2)['queries'],6)
            for key,value in [('checks',checks[:-1]),('abort_rc',0),('abort_callback_calls',0),('native_continuation_ids',[]),('official_prefix_ids',[0])]:
                write({**out,key:value})
                with self.assertRaises(ValueError):inspect(p,fixture,'x',2)
            bad=json.loads(json.dumps(out));bad['checks'][0]['inputs']=[1,999];write(bad)
            with self.assertRaisesRegex(ValueError,'confirmed prefix'):inspect(p,fixture,'x',2)
            write(out);(p/'grid-2.known-2.f32').write_bytes(data[:-4])
            with self.assertRaisesRegex(ValueError,'discrepancy'):inspect(p,fixture,'x',2)

if __name__=='__main__':unittest.main()
