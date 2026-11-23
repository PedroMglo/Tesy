#!/usr/bin/env python3
"""Discriminating controls for the prospective resource authority."""
from copy import deepcopy
import unittest

from c2_gate import GateError
from c2_server_run import protocol_cgroup_memory_max
from c9_server_admission import apply_prospective_resource_policy
from host_resource_policy import (GIB,ResourcePolicyError,derive_policy,
                                  parse_nvidia_temperature_query,parse_gpu_csv,
                                  freeze_protocol_resource_limits,
                                  validate_resource_protocol,operational_session_ready,
                                  RuntimeGuard)

QUERY='''GPU Current Temp : 40 C
GPU Current T.Limit Temp : 47 C
GPU Shutdown T.Limit Temp Specification : -12 C
GPU Slowdown T.Limit Temp Specification : -2 C
GPU Max Operating T.Limit Temp Specification : 0 C
GPU Target Temperature Specification : 87 C
Memory Current Temp : N/A'''
GPU='GPU-83d90c55-1d92-75da-fc30-7771a85f2521, 00000000:C4:00.0, RTX 4060 Laptop, 8188, 12, 40, 615.71.09'
SENSORS={'k10temp-pci-00c3':{'Tctl':{'temp1_input':45.125}},
         'nvme-pci-c100':{'Composite':{'temp1_input':35.85,'temp1_max':86.85,
                                      'temp1_crit':89.85},
                          'Sensor 1':{'temp2_max':65261.85,'temp2_min':-273.15}}}

def fixture():
    return {'memory':{'MemTotal':32698777600,'MemAvailable_min':22*GIB,
                      'MemAvailable_max':22*GIB+256*2**20,
                      'ancestor_headroom_bytes':30*GIB},
            'gpu_csv':GPU,'gpu_temperature_query':QUERY,'sensors':deepcopy(SENSORS),
            'cpu_identity':{'model':'AMD Ryzen AI 9 HX 370 w/ Radeon 890M',
                            'family':26,'model_id':36},
            'involved_nvme':{'nvme0':{'bdf':'0000:c1:00.0','model':'SSD','firmware':'A'}},
            'power':{'source':'AC','profile':'performance','online_sources':['AC0']},
            'psi':{'full_avg10':0.0}}

def builder():
    return {'limits':{'memory_max_bytes':int(16.5*GIB),'rss_max_bytes':16*GIB,
                      'gpu_max_mib':6500,'min_mem_available_bytes':6*GIB,
                      'cpu_max_c':95,'gpu_max_c':80,'nvme_max_c':70,
                      'max_gap_s':3,'min_active_s':0},
            'c9':{'cgroup_memory_max_bytes':18*GIB},
            'identity':{'model_id':'target120b'}}

def runtime_fixture():
    resources=freeze_protocol_resource_limits(derive_policy(snapshot=fixture()),
                                               cgroup_memory_max_bytes=18*GIB)
    protocol={'limits':{'max_gap_s':3},'resources':resources}
    cg={'path':'/test.scope','memory_max':18*GIB,'swap_max':0,
        'memory_current':10*GIB,'memory_peak':10*GIB,'swap_current':0,
        'events':{'max':0,'oom':0,'oom_kill':0},
        'events_local':{'max':0,'oom':0,'oom_kill':0}}
    sample={'elapsed_s':1,'cgroup':deepcopy(cg),
            'proc':{'VmRSS':8*GIB,'VmSwap':0,'VmHWM':8*GIB},
            'gpu':{'uuid':resources['gpu']['uuid'],'bdf':resources['gpu']['bdf'],
                   'used_mib':5752,'temperature_c':63},
            'thermal':{'cpu_tctl_c':95.125,
                       'nvme_composite_by_sensor':{'nvme-pci-c100':55.85}},
            'mem_available_bytes':8*GIB,
            'resource_observation':{'host_psi_full_avg10':0,
                                    'power':{'source':'AC','online_sources':['AC0'],
                                             'profile':'performance'}}}
    return protocol,cg,sample

class ProspectivePolicyTests(unittest.TestCase):
    def test_real_ada_relative_margin_and_target_separate(self):
        row=parse_nvidia_temperature_query(QUERY,current_c=40)
        self.assertEqual((row['max_operating_c'],row['slowdown_c'],row['shutdown_c'],row['stop_c']),
                         (87,89,99,89))
        self.assertEqual(row['target_c'],87)
        self.assertEqual(row['status'],'DEVICE_DERIVED_EXPERIMENT_ADMISSION')

    def test_nvidia_unavailable_fallback_and_mutants(self):
        q=QUERY.replace('GPU Shutdown T.Limit Temp Specification : -12 C',
                        'GPU Shutdown T.Limit Temp Specification : N/A')
        self.assertEqual(parse_nvidia_temperature_query(q,current_c=40)['stop_c'],80)
        self.assertIn('UNQUALIFIED',parse_nvidia_temperature_query(q,current_c=40)['status'])
        for bad in (QUERY+'\nGPU Current T.Limit Temp : 47 C',
                    QUERY.replace('GPU Slowdown T.Limit Temp Specification : -2 C',
                                  'GPU Slowdown T.Limit Temp Specification : 3 C'),
                    QUERY.replace('GPU Current T.Limit Temp : 47 C',
                                  'GPU Current T.Limit Temp : 1e309 C')):
            with self.subTest(bad=bad[-60:]),self.assertRaises(ResourcePolicyError):
                parse_nvidia_temperature_query(bad,current_c=40)
        with self.assertRaises(ResourcePolicyError):
            parse_gpu_csv('GPU,8188,12,40,driver')

    def test_policy_capacity_and_secondary_sentinel(self):
        policy=derive_policy(snapshot=fixture())
        self.assertEqual(policy['memory']['reserve_bytes'],2*GIB)
        self.assertEqual(policy['memory']['cap_max_bytes'],20*GIB)
        self.assertEqual(policy['nvme'][0]['stop_c'],87.85)
        self.assertEqual(policy['gpu']['memory_stop_total_mib'],7676)
        self.assertTrue(operational_session_ready(policy,processor_cooling_active=True)[0])
        policy['cpu']['current_c']=95.125
        self.assertEqual(operational_session_ready(policy)[1],['CPU_START_WARNING'])

    def test_v2_replaces_legacy_cap_atomically(self):
        original=builder(); before=deepcopy(original);policy=derive_policy(snapshot=fixture())
        out=apply_prospective_resource_policy(original,{'resource_policy':policy},
                                              cgroup_memory_max_bytes=20*GIB,profile_key='renamed')
        self.assertEqual(original,before)
        self.assertEqual(protocol_cgroup_memory_max(out),20*GIB)
        self.assertNotIn('cgroup_memory_max_bytes',out['c9'])
        self.assertNotIn('memory_max_bytes',out['limits'])
        self.assertEqual(out['resources']['cgroup']['memory_stop_bytes'],20*GIB-512*2**20)
        with self.assertRaises(ResourcePolicyError):
            validate_resource_protocol(dict(out,limits=dict(out['limits'],gpu_max_c=80)))
        with self.assertRaises(ResourcePolicyError):
            validate_resource_protocol(dict(out,c9={'cgroup_memory_max_bytes':18*GIB}))
        changed=deepcopy(out)
        changed['resources']['gpu']['temperature_stop_c']+=1
        with self.assertRaises(ResourcePolicyError):
            validate_resource_protocol(changed)
        changed=deepcopy(out)
        changed['resources']['inventory_snapshot']['gpu_csv']=GPU.replace('8188','8180')
        with self.assertRaises(ResourcePolicyError):
            validate_resource_protocol(changed)

    def test_invalid_caps_and_snapshots_never_mutate(self):
        policy=derive_policy(snapshot=fixture());original=builder();saved=deepcopy(original)
        for cap in (None,True,-1,19*GIB+1,21*GIB):
            with self.subTest(cap=cap),self.assertRaises((GateError,ResourcePolicyError)):
                apply_prospective_resource_policy(original,{'resource_policy':policy},
                                                  cgroup_memory_max_bytes=cap)
            self.assertEqual(original,saved)
        broken=deepcopy(policy);broken['snapshot']['memory']['MemTotal']+=1
        with self.assertRaises(ResourcePolicyError):
            freeze_protocol_resource_limits(broken,cgroup_memory_max_bytes=20*GIB)

    def test_memory_cpu_power_nvme_negatives(self):
        for mutation in ('bool','overflow','negative','cpu','power','sentinel','low_ancestor'):
            row=fixture()
            if mutation=='bool':row['memory']['MemAvailable_min']=True
            if mutation=='overflow':row['psi']['full_avg10']=float('inf')
            if mutation=='negative':row['memory']['MemAvailable_min']=-1
            if mutation=='cpu':row['cpu_identity']['model']='another CPU'
            if mutation=='power':row['power']['source']='BATTERY'
            if mutation=='sentinel':row['sensors']['nvme-pci-c100']['Composite']['temp1_crit']=65261.85
            if mutation=='low_ancestor':row['memory']['ancestor_headroom_bytes']=0
            with self.subTest(mutation=mutation),self.assertRaises(ResourcePolicyError):
                derive_policy(snapshot=row)

    def test_multiple_involved_nvme(self):
        row=fixture()
        row['involved_nvme']['nvme1']={'bdf':'0000:d2:00.0','model':'SSD2','firmware':'B'}
        row['sensors']['nvme-pci-d200']={'Composite':{'temp1_input':40,
                                                     'temp1_max':80,'temp1_crit':85}}
        self.assertEqual(len(derive_policy(snapshot=row)['nvme']),2)

    def test_runtime_warning_and_exact_boundaries(self):
        protocol,start,sample=runtime_fixture();gate=RuntimeGuard(protocol,start)
        self.assertIsNone(gate.check(sample))  # CPU95.125, normal cooling is diagnostic
        for key,mutate,reason in (
            ('cpu100',lambda s:s['thermal'].update(cpu_tctl_c=100),'CPU_TJMAX'),
            ('gpu89',lambda s:s['gpu'].update(temperature_c=89),'GPU_TEMPERATURE_ADMISSION'),
            ('nvme87',lambda s:s['thermal']['nvme_composite_by_sensor'].update(**{'nvme-pci-c100':87.85}),
             'NVME_TEMPERATURE_ADMISSION'),
            ('vram',lambda s:s['gpu'].update(used_mib=7676),'GPU_TOTAL_MEMORY'),
            ('cap',lambda s:s['cgroup'].update(memory_max=20*GIB),'CGROUP_IDENTITY_OR_CAP'),
            ('swap',lambda s:s['cgroup'].update(swap_current=1),'WORKLOAD_SWAP'),
            ('power',lambda s:s['resource_observation']['power'].update(source='BATTERY'),
             'POWER_CONDITION_CHANGED')):
            with self.subTest(key=key):
                bad=deepcopy(sample);mutate(bad)
                self.assertEqual(RuntimeGuard(protocol,start).check(bad),reason)
        bad=deepcopy(sample);bad['gpu']['used_mib']=float('inf')
        with self.assertRaises(ResourcePolicyError):RuntimeGuard(protocol,start).check(bad)

    def test_runtime_memory_and_psi_persistence(self):
        protocol,start,sample=runtime_fixture();gate=RuntimeGuard(protocol,start)
        low=deepcopy(sample);low['mem_available_bytes']=GIB-1
        self.assertIsNone(gate.check(low));low['elapsed_s']=2
        self.assertEqual(gate.check(low),'HOST_MEMORY_1GIB_PERSISTED')
        gate=RuntimeGuard(protocol,start)
        low['mem_available_bytes']=GIB+1;low['elapsed_s']=1
        self.assertIsNone(gate.check(low));low['elapsed_s']=11
        self.assertEqual(gate.check(low),'HOST_RESERVE_PERSISTED')
        gate=RuntimeGuard(protocol,start)
        low['mem_available_bytes']=8*GIB;low['resource_observation']['host_psi_full_avg10']=10
        low['elapsed_s']=1;self.assertIsNone(gate.check(low))
        low['elapsed_s']=11;self.assertEqual(gate.check(low),'HOST_PSI_PERSISTED')

if __name__=='__main__':unittest.main()
