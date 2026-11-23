"""Metadata-reader lock identity regression; mocks only inspect argv, not guards."""
import subprocess
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import residency_unit_run as r


class MetadataReaderIdentity(unittest.TestCase):
    def test_real_cli_rejects_unlocked_model_free_id_before_child(self):
        root=Path(__file__).resolve().parents[1]
        model='/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf'
        result=subprocess.run([sys.executable,str(root/'tools/run_bounded.py'),
            '--run-id','metadata-lock-negative','--model-id','model-free',
            '--backend','stock','--backend-root',str(root/'backends/c236-block-verifier-c75'),
            '--variant','metadata','--workload',str(root/'models.lock.json'),
            '--cache-condition','none','--',sys.executable,'-c',
            'raise RuntimeError("child must not execute")',model],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('model ID/path missing from lock',result.stderr)
        self.assertNotIn('child must not execute',result.stderr)

    def test_metadata_reader_keeps_original_lock_id(self):
        p={'physical_envelope_s':100,'common_env':{},'backend_root':'/fixture',
           'model_id':'gpt-oss-120b-mxfp4-gguf','claim_scope':'argv only',
           'success_status':'ARGS_INSPECTED',
           'runs':[{'id':'metadata','timeout_s':5,'inventory':True,'env':{},
                    'variant':'metadata','label':'none','command':['/bin/true']}]}
        with tempfile.TemporaryDirectory() as d, patch.object(r.subprocess,'run',
                return_value=subprocess.CompletedProcess([],0,'','')) as call:
            self.assertEqual(r.inside(Path('/fixture'),Path(d),p),0)
            argv=call.call_args.args[0]
            self.assertEqual(argv[argv.index('--model-id')+1],p['model_id'])
            self.assertIn('--collect-start-inventory',argv)
            self.assertIn('--require-telemetry',argv)

    def test_inventory_policy_hash_binding_rejects_stale_contract(self):
        root=Path(__file__).resolve().parents[1]
        old=root/'results/c250-head-conversion-lock-repair-20261004'
        new=root/'results/c251-head-conversion-policy-binding-20261004'
        previous=json.loads((old/'protocol.json').read_text())
        prospective=json.loads((new/'protocol.json').read_text())
        self.assertNotEqual(previous['start_inventory']['policy_sha256'],hashlib.sha256((old/'resource-policy.json').read_bytes()).hexdigest())
        self.assertEqual(prospective['start_inventory']['policy_sha256'],hashlib.sha256((new/'resource-policy.json').read_bytes()).hexdigest())
        self.assertEqual(prospective['resources'],json.loads((new/'resource-policy.json').read_text()))


if __name__=='__main__' :unittest.main()
