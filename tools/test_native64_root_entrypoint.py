"""Relative invocation reaches the real C2 freshness/Popen gate, without weights."""
from datetime import datetime,timezone,timedelta
from functools import partial
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock

import c2_server_run as server
import host_resource_policy
import native64_natural as natural
from c118_start_inventory import collect
from run_bounded import sha256
from test_c120_prelaunch_entrypoint import TestPrelaunchEntrypoint,SpawnReached,policy_power_sources

class RootEntrypoint(unittest.TestCase):
    def exercise(self,bad=False):
        rid='relative-entry'
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            root=Path(tmp);relative=root.relative_to(Path.cwd())
            p,c,model,pp,observation=TestPrelaunchEntrypoint().fixture(root,rid)
            # Remove only the fixture's preparatory inventory; the entrypoint must collect its own.
            for suffix in ('.start-inventory.jsonl','.start-inventory.receipt.json'):(root/'raw'/(rid+suffix)).unlink()
            c['output_root']=str((root/'raw').resolve());p['identity']['config_sha256']=server.digest(c)
            p['native64']={'profile':'A32'};pdir=root/'protocols';pdir.mkdir()
            (pdir/(rid+'.json')).write_text(json.dumps(p));(root/(rid+'-config.json')).write_text(json.dumps(c))
            (root/'workload.json').write_text('{}')
            (root/'session-input.json').write_text(json.dumps({'base_prefix_words':1,'first_question':'x',
                'increment_beta_words':1,'second_question':'y','template_date':'2026-09-30'}))
            (root/'protocol.json').write_text(json.dumps({'order':[[rid,'A32']],'source_sha256':{},'workload_sha256':sha256(root/'workload.json')}))
            (root/'freeze-manifest.json').write_text(json.dumps({'sha256':{str(x.relative_to(root)):sha256(x) for x in root.rglob('*.json')}}))
            clock=[100000.0];utc=datetime.now(timezone.utc)-timedelta(seconds=60)
            def sleep(n):clock[0]+=n
            def collect_clocked(r,k,**kw):
                receipt=collect(r,k,**kw,sample=observation,monotonic=lambda:clock[0],sleep=sleep,
                    utc_now=lambda:utc+timedelta(seconds=clock[0]-100000))
                if bad:receipt['path']=str(relative/'raw'/(rid+'.start-inventory.jsonl'))
                return receipt
            sample=observation();cg={'memory_max':18*2**30,'swap_max':0,'path':'/test'}
            spawn=MagicMock(side_effect=SpawnReached)
            with patch.object(natural,'collect',side_effect=collect_clocked),patch.object(natural,'MODEL',model), \
                 patch.object(natural,'git',return_value='measurement-fixture'),patch.object(natural,'no_other_model'), \
                 patch.object(server,'cgroup_state',return_value=cg),patch.object(server,'mem_available',return_value=26*2**30), \
                 patch.object(server,'gpu_state',return_value=sample['gpu']),patch.object(server,'thermal_state',return_value=sample['thermal']), \
                 patch.object(host_resource_policy,'host_pressure',return_value=0), \
                 patch.object(host_resource_policy,'live_power',return_value={'source':'AC','profile':'performance','online_sources':policy_power_sources(p)}), \
                 patch.object(server.socket,'socket'),patch.object(server.subprocess,'Popen',spawn):
                self.assertEqual(natural.arm(relative,rid,'measurement-fixture'),1) # fixture intentionally stops at Popen
            self.assertEqual(spawn.call_count,0 if bad else 1)
            receipt=json.loads((root/'raw'/(rid+'.start-inventory.receipt.json')).read_text())
            if not bad:self.assertEqual(receipt['path'],str(root/'raw'/(rid+'.start-inventory.jsonl')))
            result=json.loads((root/(rid+'-receipt.json')).read_text())
            self.assertIn('identity/hash' if bad else 'SpawnReached',result['reason'])

    def test_relative_invocation_normalizes_before_collect_and_internal_launch_gate(self):self.exercise()
    def test_relative_receipt_alias_remains_invalid(self):self.exercise(bad=True)

if __name__=='__main__':unittest.main()
