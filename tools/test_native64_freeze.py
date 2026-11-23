import json
from pathlib import Path
import tempfile
import time
import unittest
from epoch_accounting import Epoch
from native64_natural import require_freeze
from run_bounded import sha256

class FreezeTests(unittest.TestCase):
    def test_artifact_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=r/'protocol.json';p.write_text('{"cap":18}')
            (r/'freeze-manifest.json').write_text(json.dumps({'sha256':{'protocol.json':sha256(p)}}))
            require_freeze(r);p.write_text('{"cap":20}')
            with self.assertRaisesRegex(ValueError,'artifact changed'):require_freeze(r)
    def test_unknown_endpoints_get_no_dedup_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)/'results'/'epoch';r.mkdir(parents=True)
            (r/'epoch.json').write_text(json.dumps({'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'start_monotonic_s':time.monotonic(),'closure_reserve_s':150,'physical_limit_s':4500,
                'wall_limit_s':10800,'raw_limit_bytes':2**30}))
            rows=[{'start':{'monotonic_s':a},'end':{'monotonic_s':b},'live':True,'physical_charge_s':b-a} for a,b in ((0,10),(5,15))]
            rows.append({'start':None,'end':None,'live':True,'physical_charge_s':4})
            (r/'ledger.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
            self.assertEqual(Epoch(r).budget()['physical_used_s'],19)

if __name__=='__main__':unittest.main()
