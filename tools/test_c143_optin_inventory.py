"""Real new run_bounded spawn gate, sensor/clock/process fixtures only."""
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile
from unittest.mock import patch,MagicMock
import unittest
import sys

import run_bounded as bounded
import c118_start_inventory as inventory
from c2_gate import GateError,strict_json
from run_bounded import sha256

class SpawnReached(Exception):pass

class InventoryEntrypoint(unittest.TestCase):
    def exercise(self,bad=None):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'raw').mkdir()
            repo=Path(__file__).resolve().parents[0]
            old=Path.cwd()/'results/c117-operational-nominal-server-20260929T1058Z'
            policy=strict_json((old/'resource-policy.json').read_text());(root/'resource-policy.json').write_text(json.dumps(policy))
            p=strict_json((old/'protocols/c117-p1-control.json').read_text())
            p['start_inventory']={'schema':'c120-start-inventory-v1','duration_s':60,'max_age_s':3,'policy_sha256':sha256(root/'resource-policy.json')}
            (root/'protocol.json').write_text(json.dumps(p));(root/'preset.json').write_text('{}')
            clock=[100000.0];origin=datetime.now(timezone.utc)-timedelta(seconds=60)
            def sample():
                return {'thermal':{'cpu_tctl_c':50,'nvme_composite_by_sensor':{r['sensor']:40 for r in policy['nvme']}},
                    'gpu':{'uuid':policy['gpu']['uuid'],'bdf':policy['gpu']['bdf'],'temperature_c':45,'used_mib':12},
                    'power':{'source':'AC','profile':'performance','online_sources':p['resources']['power']['online_sources']},'mem_available_bytes':26*2**30}
            real=inventory.collect
            def producer(*args,**kw):
                if bad=='cap':kw['cap_bytes']+=1
                if bad in ('sensor','hot_start'):
                    broken=sample();broken['thermal']['cpu_tctl_c']=120 if bad=='sensor' else 96
                    kw['sample']=lambda:broken
                else:kw['sample']=sample
                kw.update(monotonic=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n),
                          utc_now=lambda:origin+timedelta(seconds=clock[0]-100000))
                r=real(*args,**kw)
                if bad=='old':r['last_utc']=(datetime.fromisoformat(r['last_utc'])-timedelta(hours=1)).isoformat()
                if bad=='arm':r['run_id']='other'
                if bad=='scope':cg['path']='/other'
                if bad=='protocol':
                    altered=json.loads((root/'protocol.json').read_text());altered['fixture_changed']=True
                    (root/'protocol.json').write_text(json.dumps(altered))
                return r
            argv=['run_bounded.py','--run-id','tesy-test-optin','--model-id','model-free','--backend','stock',
                '--backend-root',str(Path.cwd()),'--output-root',str(root/'raw'),'--variant','model-free',
                '--workload',str(root/'preset.json'),'--cache-condition','fixture','--resource-protocol',str(root/'protocol.json'),
                '--require-telemetry','--collect-start-inventory','--','/bin/true']
            spawn=MagicMock(side_effect=SpawnReached)
            original_popen=bounded.subprocess.Popen
            def filtered_popen(command,*args,**kwargs):
                if command[0]=='/bin/true': return spawn(command,*args,**kwargs)
                return original_popen(command,*args,**kwargs)
            cg={'memory_max':18*2**30,'swap_max':0,'memory_peak':0,'path':'/fixture'}
            with patch.object(sys,'argv',argv),patch.object(inventory,'collect',producer), \
                 patch.object(bounded,'cgroup_state',side_effect=lambda:dict(cg)),patch.object(bounded,'gpu_state',return_value=sample()['gpu']), \
                 patch.object(bounded,'thermal_state',return_value=sample()['thermal']),patch.object(bounded,'mem_available',return_value=26*2**30), \
                 patch.object(bounded,'live_power',return_value={**sample()['power'],'online_sources':p['resources']['power']['online_sources']}), \
                 patch.object(bounded,'host_pressure',return_value=0),patch.object(bounded.subprocess,'Popen',filtered_popen):
                if bad is None:
                    with self.assertRaises(SpawnReached):bounded.main()
                    self.assertEqual(spawn.call_count,1)
                    self.assertTrue((root/'raw/tesy-test-optin.start-inventory.receipt.json').is_file())
                else:
                    with self.assertRaises((GateError,RuntimeError)):bounded.main()
                    self.assertEqual(spawn.call_count,0)
    def test_positive_real_entrypoint(self):self.exercise()
    def test_invalid_inventory_prevents_launch(self):
        for bad in ('sensor','cap','old','arm','scope','protocol','hot_start'):
            with self.subTest(bad=bad):self.exercise(bad)

if __name__=='__main__':unittest.main()
