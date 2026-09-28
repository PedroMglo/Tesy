"""C74 three-pair prospective gain and same-profile controls."""
import json
from pathlib import Path
import tempfile
import unittest

from c2_gate import GateError
from c74_wave_confirmation import ARMS, paired, run_id


class C74Confirmation(unittest.TestCase):
    def test_three_new_pairs_and_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'raw').mkdir(); receipts=[]
            for case,pair,wave in ARMS:
                name=run_id(case,pair,wave)
                (root/'raw'/(name+'.f32')).write_bytes(b'complete-logits')
                sample={'thermal':{'cpu_tctl_c':70.0,
                    'nvme_composite_by_sensor':{'nvme0':45.0}},
                    'gpu':{'temperature_c':50.0}}
                (root/'raw'/(name+'.samples.jsonl')).write_text(json.dumps(sample)+'\n')
                value=100.0 if wave=='off' else 90.0
                receipts.append({'run_id':name,'source':{'timing_s':
                    {'work':value,'prefill':value*0.7,'decode32':value*0.3}}})
            result=paired(root,receipts)
            self.assertTrue(all(x['status']=='CONFIRMED_TESTED_SCOPE'
                for x in result['cases'].values()))
            (root/'raw'/(run_id('warm154',3,'on')+'.f32')).write_bytes(b'mismatch')
            with self.assertRaisesRegex(GateError,'FAIL_SAME_PROFILE_FIDELITY'):
                paired(root,receipts)


if __name__=='__main__':
    unittest.main()
