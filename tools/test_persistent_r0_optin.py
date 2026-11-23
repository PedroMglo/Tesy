"""Prospective persistent R0 entrypoint contract; no weights loaded."""
import json,os,tempfile,unittest,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import c143_slots40_optin as launcher
from optin_integration_client import validate_client_contract,natural_completion,persistent_mappings
from c2_gate import GateError
from parallel_runtime import validate_launch_runtime
from host_resource_policy import validate_resource_protocol

class PersistentR0Tests(unittest.TestCase):
    def tearDown(self):launcher.select_profile('slots40')
    def test_explicit_profile_cap_and_original_default(self):
        old=launcher.BACKEND
        for cap in (None,18*2**30,19*2**30):
            with self.assertRaises(GateError):launcher.select_profile('slots40-persistent',cap)
        launcher.select_profile('slots40-persistent',20*2**30)
        self.assertEqual(launcher.CAP,20*2**30);self.assertIn('c269',str(launcher.BACKEND))
        launcher.select_profile('slots40');self.assertEqual(launcher.CAP,18*2**30);self.assertEqual(launcher.BACKEND,old)
    def test_real_preset_builder_and_verify_persistent_contract(self):
        launcher.select_profile('slots40-persistent',20*2**30)
        p,c,stat=launcher.identity()
        source=launcher.REPO/'results/c276-post-c274-r2-causal-qualification-20261005T204839Z/stable-inventory'
        def inventory(root):
            for name in ('snapshot.json','resource-policy.json'):shutil.copy2(source/name,root/name)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'session'
            with patch.dict(os.environ,{},clear=True),patch.object(launcher,'no_other_model'),patch.object(launcher.c55_inventory,'run',inventory),patch.object(launcher.os,'statvfs',return_value=SimpleNamespace(f_bavail=50*2**30,f_frsize=1)):
                launcher.prepare(root,18442,480)
                preset=launcher.verified(root)
                protocol=json.loads((root/'resource-protocol.json').read_text());validate_resource_protocol(protocol)
                self.assertEqual(protocol['resources']['cgroup']['memory_high_bytes'],20*2**30)
                self.assertEqual(protocol['parallel_runtime'],p['parallel_runtime']);self.assertEqual(preset['extra_library_sha256'],p['extra_library_sha256'])
                self.assertEqual(preset['server_command'][preset['server_command'].index('-ub')+1],'32')
                self.assertEqual(preset['server_command'][preset['server_command'].index('--moe-stream-cache')+1],'40s')
                with patch.dict(os.environ,{'GOMP_SPINCOUNT':'0'}):
                    with self.assertRaises(GateError):launcher.verified(root)
                protocol['parallel_runtime']['environment']['values']['OMP_WAIT_POLICY']='PASSIVE'
                (root/'resource-protocol.json').write_text(json.dumps(protocol))
                with self.assertRaises(GateError):launcher.verified(root)
    def test_missing_persistent_manifest_and_library_fail_closed(self):
        launcher.select_profile('slots40-persistent',20*2**30)
        with patch.object(launcher,'SOURCE',Path('/nonexistent-persistent-manifest')):
            with self.assertRaisesRegex(GateError,'manifest absent'):launcher.identity()
        p,c,s=launcher.identity();p['extra_library_sha256']={'/absent-library':'0'*64}
        real=launcher.strict_json
        with patch.object(launcher,'strict_json',side_effect=lambda text:p if 'extra_library_sha256' in text else real(text)):
            with self.assertRaisesRegex(GateError,'dependency missing'):launcher.identity()
    def test_exact_client_cardinality(self):
        self.assertEqual(validate_client_contract({'expected_request_count':2,'tasks':[{'id':'A'},{'id':'B'}]}),2)
        for tasks in ([],[{'id':'A'}],[{'id':'A'},{'id':'A'}],[{'id':'A'},{'id':'B'},{'id':'C'}]):
            with self.assertRaises(GateError):validate_client_contract({'expected_request_count':2,'tasks':tasks})
    def test_natural_cap_boundary_and_historical_policy(self):
        item={'finish_reason':'stop','usage':{'completion_tokens':256}}
        natural_completion(item,256,True)
        with self.assertRaises(GateError):natural_completion(item,256,False)
        for finish,n in [('length',256),('stop',0),('stop',257),('stop',float('nan')),('stop',True)]:
            with self.assertRaises(GateError):natural_completion({'finish_reason':finish,'usage':{'completion_tokens':n}},256,True)
    def test_mapped_dependency_missing_rejected(self):
        with self.assertRaises(GateError):persistent_mappings(os.getpid(),{'extra_library_sha256':{'/absent-library':'0'*64}})

if __name__=='__main__':unittest.main()
