"""Exercise the existing resource authority and real bounded entrypoint."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import run_bounded as bounded
from host_resource_policy import RuntimeGuard, ResourcePolicyError, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from test_host_resource_policy import fixture, runtime_fixture

def paging():
    p,cg,s=runtime_fixture()
    p['resources']=freeze_protocol_resource_limits(derive_policy(snapshot=fixture()),cgroup_memory_max_bytes=18*2**30,execution_class='FILE_PAGING')
    cg['memory_high']=p['resources']['cgroup']['memory_high_bytes']
    s['cgroup']=deepcopy(cg)
    return p,cg,s

class FilePaging(unittest.TestCase):
    def test_reclaim_and_peak_allowed_oom_swap_pressure_stop(self):
        p,cg,s=paging();cap=p['resources']['cgroup']['memory_max_bytes']
        s['cgroup']['memory_current']=cap;s['cgroup']['memory_peak']=cap+4096
        s['cgroup']['events']['max']=100;s['cgroup']['events']['high']=1000
        s['cgroup']['pressure']={'full':{'avg10':90}}
        self.assertIsNone(RuntimeGuard(p,cg).check(s))
        for field in ('oom','oom_kill'):
            x=deepcopy(s);x['cgroup']['events'][field]=1
            self.assertEqual(RuntimeGuard(p,cg).check(x),'CGROUP_EVENT')
        x=deepcopy(s);x['proc']['VmSwap']=4096
        self.assertEqual(RuntimeGuard(p,cg).check(x),'WORKLOAD_SWAP')
        x=deepcopy(s);x['resource_observation']['host_psi_full_avg10']=11
        guard=RuntimeGuard(p,cg);self.assertIsNone(guard.check(x));x['elapsed_s']=12
        self.assertEqual(guard.check(x),'HOST_PSI_PERSISTED')

    def test_streaming_semantics_preserved(self):
        p,cg,s=runtime_fixture();s['cgroup']['events']['max']=1
        self.assertEqual(RuntimeGuard(p,cg).check(s),'CGROUP_EVENT')
        s['cgroup']['events']['max']=0;s['cgroup']['memory_peak']=18*2**30
        self.assertEqual(RuntimeGuard(p,cg).check(s),'CGROUP_PREVENTIVE_MARGIN')

    def test_single_authority_mutants(self):
        p,cg,s=paging();validate_resource_protocol(p)
        for key in ('memory_high_bytes','memory_max_bytes','memory_swap_max_bytes'):
            x=deepcopy(p);x['resources']['cgroup'][key]+=1
            with self.assertRaises(ResourcePolicyError):validate_resource_protocol(x)
        s['cgroup']['memory_high']+=1
        self.assertEqual(RuntimeGuard(p,cg).check(s),'CGROUP_HIGH_INCONSISTENT')

    def test_full_monitor_entrypoint_blocks_bad_scope_cap_high_before_popen(self):
        for bad in (None,'cap','high','swap','scope'):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as t:
                root=Path(t);p,cg,s=paging();cg['memory_peak']=0;s['thermal']['cpu_tctl_c']=50
                if bad=='scope':p['execution_scope_unit']='expected'
                elif bad:cg[{'cap':'memory_max','high':'memory_high','swap':'swap_max'}[bad]]+=1
                protocol=root/'protocol.json';protocol.write_text(json.dumps(p))
                argv=['run_bounded','--run-id','c147-fixture','--model-id','dummy','--backend','stock',
                      '--backend-root',str(Path.cwd()),'--output-root',str(root/'raw'),'--variant','fixture',
                      '--workload',str(protocol),'--cache-condition','fixture','--resource-protocol',str(protocol),
                      '--require-telemetry','--','/bin/sleep','1']
                class Reached(Exception):pass
                spy=MagicMock(side_effect=Reached);original=bounded.subprocess.Popen
                def spawn(cmd,*a,**kw):
                    return spy(cmd,*a,**kw) if cmd[0]=='/bin/sleep' else original(cmd,*a,**kw)
                with patch.object(sys,'argv',argv),patch.object(bounded,'cgroup_state',return_value=cg),\
                     patch.object(bounded,'gpu_state',return_value=s['gpu']),patch.object(bounded,'thermal_state',return_value=s['thermal']),\
                     patch.object(bounded,'mem_available',return_value=26*2**30),patch.object(bounded,'host_pressure',return_value=0),\
                     patch.object(bounded,'live_power',return_value=p['resources']['power']),patch.object(bounded.subprocess,'Popen',spawn):
                    with self.assertRaises(SystemExit if bad else Reached):bounded.main()
                    self.assertEqual(spy.call_count,0 if bad else 1)

    def test_endpoint_reclaim_and_oom(self):
        p,cg,s=paging();end=deepcopy(cg);end['events']['max']=10
        self.assertIsNone(bounded.prospective_endpoint_reason(.1,1,1.1,end,cg,p['resources']))
        end['events']['oom']=1
        self.assertEqual(bounded.prospective_endpoint_reason(.1,1,1.1,end,cg,p['resources']),'PROSPECTIVE_CGROUP_END_EVENT')

    def test_stop_checks_actual_process_identity(self):
        process=MagicMock();process.poll.return_value=None;process.pid=123;process._tesy_identity={'pid':123};process._tesy_executable='/bin/sleep'
        with patch.object(bounded,'process_identity',return_value={'pid':124}),patch.object(bounded.os,'killpg') as kill:
            with self.assertRaises(RuntimeError):bounded.stop_own_group(process)
            kill.assert_not_called()

if __name__=='__main__':unittest.main()
