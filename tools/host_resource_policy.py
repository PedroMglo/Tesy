#!/usr/bin/env python3
"""Prospective resource authority. Historical protocols retain their own rules."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

GIB = 2**30
MIB = 2**20
Q = 256*MIB
CPU_MODEL = 'AMD Ryzen AI 9 HX 370 w/ Radeon 890M'
LEGACY_KEYS = frozenset(('memory_max_bytes','rss_max_bytes','gpu_max_mib',
                         'min_mem_available_bytes','cpu_max_c','gpu_max_c','nvme_max_c'))

class ResourcePolicyError(ValueError):
    pass

def finite(value, label, low=None, high=None):
    if type(value) not in (int,float) or not math.isfinite(value) or \
       (low is not None and value < low) or (high is not None and value > high):
        raise ResourcePolicyError(f'{label}: finite value out of range')
    return float(value)

def integer(value, label, low=0):
    if type(value) is not int or value < low:
        raise ResourcePolicyError(f'{label}: integer >= {low} required')
    return value

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()

def temp(value,label):
    return finite(value,label,0,120)

def parse_nvidia_temperature_query(text, *, current_c):
    """Ada T.Limit values are margins, not absolute Celsius temperatures."""
    if type(text) is not str:
        raise ResourcePolicyError('NVIDIA query absent')
    labels={'GPU Current T.Limit Temp':'margin',
            'GPU Shutdown T.Limit Temp Specification':'shutdown_offset',
            'GPU Slowdown T.Limit Temp Specification':'slowdown_offset',
            'GPU Max Operating T.Limit Temp Specification':'maxop_offset',
            'GPU Shutdown Temp':'shutdown_abs','GPU Slowdown Temp':'slowdown_abs',
            'GPU Max Operating Temp':'maxop_abs',
            'GPU Target Temperature Specification':'target'}
    found={}; raw={}
    for line in text.splitlines():
        if ':' not in line:continue
        label,value=(part.strip() for part in line.split(':',1))
        key=labels.get(label)
        if key is None:continue
        if key in found:raise ResourcePolicyError('duplicate GPU threshold: '+label)
        raw[key]=value
        if value=='N/A':found[key]=None;continue
        match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*C',value)
        if match is None:raise ResourcePolicyError('invalid GPU threshold: '+label)
        number=finite(float(match.group(1)),label)
        found[key]=number if key.endswith('_offset') or key=='margin' else temp(number,label)
    if not found:raise ResourcePolicyError('GPU threshold labels absent')
    current=temp(current_c,'GPU current')
    def absolute(name):
        direct=found.get(name+'_abs'); margin=found.get('margin'); offset=found.get(name+'_offset')
        derived=temp(current+margin-offset,name+' from T.Limit') if margin is not None and offset is not None else None
        if direct is not None and derived is not None and abs(direct-derived)>2:
            raise ResourcePolicyError('contradictory GPU '+name)
        return direct if direct is not None else derived
    maxop,slow,shutdown=(absolute(x) for x in ('maxop','slowdown','shutdown'))
    if any(a is not None and b is not None and a>b for a,b in
           ((maxop,slow),(slow,shutdown),(maxop,shutdown))):
        raise ResourcePolicyError('impossible GPU thermal order')
    if slow is None or shutdown is None:
        stop,status=80.0,'THERMAL_LIMITS_UNQUALIFIED_LOCAL_FALLBACK'
    else:
        stop,status=min(slow,shutdown-5),'DEVICE_DERIVED_EXPERIMENT_ADMISSION'
    if stop<=current:raise ResourcePolicyError('GPU at/above admission stop')
    return {'current_c':current,'margin_c':found.get('margin'),'max_operating_c':maxop,
            'slowdown_c':slow,'shutdown_c':shutdown,'target_c':found.get('target'),
            'warning_c':maxop,'stop_c':stop,'status':status,'raw_labels':raw,
            'source':'nvidia-smi -q -d TEMPERATURE; T.Limit relative to maximum operating'}

def parse_gpu_csv(row):
    if type(row) is not str or len(row.splitlines())!=1:
        raise ResourcePolicyError('one GPU CSV row required')
    parts=[x.strip() for x in row.split(',')]
    if len(parts)!=7:raise ResourcePolicyError('GPU CSV needs UUID,BDF,name,total,used,temp,driver')
    uuid,bdf,name,total,used,current,driver=parts
    if not re.fullmatch(r'GPU-[0-9a-fA-F-]{36}',uuid) or \
       not re.fullmatch(r'[0-9a-fA-F]{8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]',bdf) or \
       not name or not driver:
        raise ResourcePolicyError('GPU identity missing')
    total=finite(float(total),'GPU total MiB',1024)
    used=finite(float(used),'GPU used MiB',0,total)
    return {'uuid':uuid,'bdf':bdf,'name':name,'driver':driver,'total_mib':total,
            'used_mib':used,'temperature_c':temp(float(current),'GPU current')}

def parse_cpu(sensors, identity):
    if identity.get('model')!=CPU_MODEL or identity.get('family')!=26 or identity.get('model_id')!=36:
        raise ResourcePolicyError('CPU identity not verified HX370')
    rows=[]
    for name,data in sensors.items():
        if name.startswith('k10temp-') and type(data) is dict and \
           type(data.get('Tctl')) is dict and 'temp1_input' in data['Tctl']:
            rows.append((name,temp(data['Tctl']['temp1_input'],'Tctl')))
    if len(rows)!=1:raise ResourcePolicyError('unique Tctl sensor required')
    return {'sensor':rows[0][0],'model':identity['model'],'family':26,'model_id':36,
            'driver':'k10temp','current_c':rows[0][1],'warning_c':95.0,'stop_c':100.0,
            'source':'AMD HX370 Tjmax; Tctl, no assumed Tdie offset'}

def parse_nvme(sensors,involved):
    if type(involved) is not dict or not involved:
        raise ResourcePolicyError('involved NVMe identity absent')
    out=[]
    for controller,identity in sorted(involved.items()):
        if not re.fullmatch(r'nvme\d+',controller) or type(identity) is not dict:
            raise ResourcePolicyError('NVMe controller malformed')
        bdf=identity.get('bdf')
        if type(bdf) is not str or not re.fullmatch(r'[0-9a-fA-F]{4,8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]',bdf):
            raise ResourcePolicyError('NVMe BDF absent')
        _,bus,device_fn=bdf.split(':')
        short=bus+device_fn.split('.')[0]
        rows=[(name,data['Composite']) for name,data in sensors.items()
              if name.startswith('nvme-pci-') and name.split('-pci-')[-1].lower()==short.lower()
              and type(data) is dict and type(data.get('Composite')) is dict]
        if len(rows)!=1:raise ResourcePolicyError('NVMe Composite sensor missing/ambiguous')
        name,data=rows[0]
        current=temp(data.get('temp1_input'),name+' current')
        warning=temp(data['temp1_max'],name+' warning') if data.get('temp1_max') is not None else None
        critical=temp(data['temp1_crit'],name+' critical') if data.get('temp1_crit') is not None else None
        if critical is None or critical-2<=current or warning is not None and warning>critical:
            raise ResourcePolicyError('NVMe threshold invalid')
        out.append({'controller':controller,'bdf':bdf,'model':identity.get('model'),
                    'firmware':identity.get('firmware'),'sensor':name,'current_c':current,
                    'warning_c':warning,'critical_c':critical,'stop_c':critical-2,
                    'source':'Composite critical minus 2C admission; max is warning'})
    return out

def derive_policy(*,snapshot):
    if type(snapshot) is not dict:raise ResourcePolicyError('snapshot object required')
    memory=snapshot.get('memory',{})
    total=integer(memory.get('MemTotal'),'MemTotal',1)
    minimum=integer(memory.get('MemAvailable_min'),'MemAvailable_min')
    maximum=integer(memory.get('MemAvailable_max'),'MemAvailable_max')
    ancestor=integer(memory.get('ancestor_headroom_bytes'),'ancestor headroom',1)
    if not 0<minimum<=maximum<=total:raise ResourcePolicyError('memory baseline impossible')
    reserve=max(2*GIB,maximum-minimum+GIB)
    cap_max=max(0,min(minimum-reserve,total-reserve,ancestor))//Q*Q
    if cap_max<=0:raise ResourcePolicyError('host cap unavailable')
    sensors=snapshot.get('sensors')
    if type(sensors) is not dict:raise ResourcePolicyError('sensors missing')
    gpu=parse_gpu_csv(snapshot.get('gpu_csv'))
    gpu.update(parse_nvidia_temperature_query(snapshot.get('gpu_temperature_query'),
                                              current_c=gpu['temperature_c']))
    gpu['memory_stop_total_mib']=gpu['total_mib']-512
    if gpu['used_mib']>=gpu['memory_stop_total_mib']:
        raise ResourcePolicyError('GPU reserve unavailable')
    cpu=parse_cpu(sensors,snapshot.get('cpu_identity',{}))
    nvme=parse_nvme(sensors,snapshot.get('involved_nvme'))
    power=snapshot.get('power')
    if type(power) is not dict or power.get('source')!='AC' or \
       power.get('profile')!='performance' or not power.get('online_sources'):
        raise ResourcePolicyError('AC/performance source not fixed')
    psi=snapshot.get('psi',{})
    finite(psi.get('full_avg10'),'PSI full avg10',0,100)
    return {'schema':'tesy-resource-inventory-v2','snapshot_sha256':digest(snapshot),
            'snapshot':deepcopy(snapshot),'cpu':cpu,'gpu':gpu,'nvme':nvme,
            'power':deepcopy(power),'psi':deepcopy(psi),
            'memory':{'total_bytes':total,'available_min_bytes':minimum,
                      'available_max_bytes':maximum,'external_variation_bytes':maximum-minimum,
                      'reserve_bytes':reserve,'ancestor_headroom_bytes':ancestor,
                      'cap_max_bytes':cap_max}}

def freeze_protocol_resource_limits(policy,*,cgroup_memory_max_bytes,
                                    start_mode='OPERATIONAL_SESSION_START'):
    if type(policy) is not dict or policy.get('schema')!='tesy-resource-inventory-v2' or \
       digest(policy.get('snapshot'))!=policy.get('snapshot_sha256'):
        raise ResourcePolicyError('inventory snapshot/hash invalid')
    if policy != derive_policy(snapshot=policy['snapshot']):
        raise ResourcePolicyError('inventory derivation differs from snapshot')
    cap=integer(cgroup_memory_max_bytes,'cgroup cap',GIB)
    if cap%Q or cap>policy['memory']['cap_max_bytes']:
        raise ResourcePolicyError('cap not admitted or not 256MiB aligned')
    if start_mode not in ('OPERATIONAL_SESSION_START','CAPACITY_ADMISSION_START','CAUSAL_AB_START'):
        raise ResourcePolicyError('start mode invalid')
    gpu,cpu=policy['gpu'],policy['cpu']
    return {'schema':'tesy-resources-v2','snapshot_sha256':policy['snapshot_sha256'],
            'inventory_snapshot':deepcopy(policy['snapshot']),
            'cgroup':{'memory_max_bytes':cap,'memory_swap_max_bytes':0,
                      'memory_stop_bytes':cap-512*MIB,'memory_high_bytes':cap},
            'memory':{'reserve_bytes':policy['memory']['reserve_bytes'],
                      'available_stop_bytes':GIB,'available_stop_samples':2,
                      'reserve_stop_duration_s':10,'psi_full_avg10_stop_percent':10,
                      'psi_stop_duration_s':10},
            'gpu':{'uuid':gpu['uuid'],'bdf':gpu['bdf'],
                   'memory_total_mib':gpu['total_mib'],
                   'memory_stop_total_mib':gpu['memory_stop_total_mib'],
                   'temperature_stop_c':gpu['stop_c'],
                   'temperature_warning_c':gpu['warning_c'],
                   'thermal_status':gpu['status']},
            'cpu':{'model':cpu['model'],'sensor':cpu['sensor'],
                   'temperature_warning_c':95.0,'temperature_stop_c':100.0},
            'nvme':[{k:row[k] for k in ('controller','bdf','sensor','stop_c',
                                       'warning_c','critical_c')} for row in policy['nvme']],
            'power':{'source':'AC','profile':'performance',
                     'online_sources':policy['power']['online_sources']},
            'start':{'mode':start_mode,'inventory_duration_s':60,
                     'initial_cpu_below_warning':True,
                     'initial_gpu_below_warning_when_available':True,
                     'initial_nvme_below_warning_when_available':True},
            'telemetry':{'max_gap_s':3,'retry_reads':1,'loss_persistence_s':3},
            'comparators':{'temperature':'>=','gpu_memory':'>=',
                           'cgroup_margin':'>=','host_available':'<'},
            'classes':{'cpu_100':'DEVICE_LIMIT','cpu_95':'WARNING',
                       'gpu_stop':'EXPERIMENT_ADMISSION',
                       'cgroup_cap':'EXPERIMENT_ADMISSION',
                       'nvme_stop':'EXPERIMENT_ADMISSION'},
            'units':{'memory':'bytes','gpu_memory':'MiB','temperature':'C','time':'s'}}

def validate_resource_protocol(protocol):
    r=protocol.get('resources') if type(protocol) is dict else None
    if type(r) is not dict or r.get('schema')!='tesy-resources-v2':
        raise ResourcePolicyError('v2 resources authority absent')
    required={'schema','snapshot_sha256','inventory_snapshot','cgroup','memory','gpu','cpu','nvme',
              'power','start','telemetry','comparators','classes','units'}
    if set(r)!=required:
        raise ResourcePolicyError('v2 resources fields missing/extra')
    cap=integer(r.get('cgroup',{}).get('memory_max_bytes'),'frozen cap',GIB)
    if cap%Q or r['cgroup'].get('memory_swap_max_bytes')!=0 or \
       r['cgroup'].get('memory_stop_bytes')!=cap-512*MIB or \
       r['cgroup'].get('memory_high_bytes')!=cap:
        raise ResourcePolicyError('cgroup authority inconsistent')
    if type(r.get('snapshot_sha256')) is not str or \
       re.fullmatch(r'[0-9a-f]{64}',r['snapshot_sha256']) is None:
        raise ResourcePolicyError('snapshot hash absent')
    if type(protocol.get('limits')) is not dict or LEGACY_KEYS.intersection(protocol['limits']):
        raise ResourcePolicyError('duplicate legacy resource limits')
    for key,value in protocol.items():
        if key not in ('resources','limits') and type(value) is dict and \
           'cgroup_memory_max_bytes' in value:
            raise ResourcePolicyError('duplicate profile cap')
    for key in ('temperature_stop_c','memory_stop_total_mib'):
        finite(r['gpu'][key],key,0)
    if type(r['gpu'].get('uuid')) is not str or type(r['gpu'].get('bdf')) is not str or \
       r['gpu']['memory_stop_total_mib']!=r['gpu']['memory_total_mib']-512:
        raise ResourcePolicyError('GPU identity/memory reserve invalid')
    finite(r['cpu']['temperature_stop_c'],'CPU stop',0,120)
    if r['cpu']['model']!=CPU_MODEL or r['cpu']['temperature_warning_c']!=95 or \
       r['cpu']['temperature_stop_c']!=100:
        raise ResourcePolicyError('CPU model/threshold invalid')
    if type(r['nvme']) is not list or not r['nvme'] or \
       len({x['sensor'] for x in r['nvme']})!=len(r['nvme']):
        raise ResourcePolicyError('NVMe monitor set invalid')
    for row in r['nvme']:finite(row['stop_c'],'NVMe stop',0,120)
    mem=r['memory']
    for key in ('reserve_bytes','available_stop_bytes','available_stop_samples',
                'reserve_stop_duration_s','psi_stop_duration_s'):
        integer(mem.get(key),'memory '+key,1)
    finite(mem.get('psi_full_avg10_stop_percent'),'memory PSI',0,100)
    if r['power']['source']!='AC' or r['power']['profile']!='performance' or \
       type(r['power']['online_sources']) is not list or not r['power']['online_sources']:
        raise ResourcePolicyError('power authority invalid')
    if r['start']['mode'] not in ('OPERATIONAL_SESSION_START','CAPACITY_ADMISSION_START',
                                'CAUSAL_AB_START') or r['start']['inventory_duration_s']!=60:
        raise ResourcePolicyError('start mode/inventory invalid')
    if r['telemetry']!={'max_gap_s':3,'retry_reads':1,'loss_persistence_s':3}:
        raise ResourcePolicyError('telemetry policy invalid')
    if r['comparators']!={'temperature':'>=','gpu_memory':'>=',
                           'cgroup_margin':'>=','host_available':'<'}:
        raise ResourcePolicyError('resource comparators invalid')
    try:
        expected=freeze_protocol_resource_limits(
            derive_policy(snapshot=r['inventory_snapshot']),
            cgroup_memory_max_bytes=cap,start_mode=r['start']['mode'])
    except (KeyError,TypeError,ValueError) as exc:
        raise ResourcePolicyError('inventory snapshot cannot reproduce resource authority') from exc
    if r!=expected:
        raise ResourcePolicyError('resource authority differs from frozen inventory derivation')
    return r

def apply_prospective_resource_policy(protocol,policy,*,cgroup_memory_max_bytes,
                                      start_mode='OPERATIONAL_SESSION_START'):
    """Copy and validate entirely before returning; caller stays untouched on error."""
    if type(protocol) is not dict or 'resources' in protocol:
        raise ResourcePolicyError('new builder protocol required')
    frozen=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=cgroup_memory_max_bytes,
                                           start_mode=start_mode)
    out=deepcopy(protocol)
    if type(out.get('limits')) is not dict:raise ResourcePolicyError('builder limits missing')
    for key in LEGACY_KEYS:out['limits'].pop(key,None)
    for key,value in out.items():
        if type(value) is dict and key not in ('limits','identity') and \
           'cgroup_memory_max_bytes' in value:
            if key!='c9':
                raise ResourcePolicyError('unexpected legacy profile cap')
            value.pop('cgroup_memory_max_bytes')
    out['resources']=frozen
    validate_resource_protocol(out)
    return out

def ready_for_launch(policy):
    reasons=[]
    if policy['cpu']['current_c']>=policy['cpu']['stop_c']:reasons.append('CPU_TJMAX')
    if policy['gpu']['temperature_c']>=policy['gpu']['stop_c']:reasons.append('GPU_TEMPERATURE')
    if policy['gpu']['used_mib']>=policy['gpu']['memory_stop_total_mib']:reasons.append('GPU_MEMORY')
    for row in policy['nvme']:
        if row['current_c']>=row['stop_c']:reasons.append('NVME_TEMPERATURE:'+row['controller'])
    return not reasons,reasons

def operational_session_ready(policy,*,processor_cooling_active=False):
    ok,reasons=ready_for_launch(policy)
    reasons=list(reasons)
    if policy['cpu']['current_c']>=policy['cpu']['warning_c']:reasons.append('CPU_START_WARNING')
    gpu=policy['gpu']
    if gpu['warning_c'] is not None and gpu['temperature_c']>=gpu['warning_c']:
        reasons.append('GPU_START_WARNING')
    for row in policy['nvme']:
        if row['warning_c'] is not None and row['current_c']>=row['warning_c']:
            reasons.append('NVME_START_WARNING:'+row['controller'])
    # Cooling state is recorded, not a failure by itself.
    return ok and not reasons,reasons

def validate_start_observation(protocol,*,available_bytes,gpu,thermal,power,psi_full_avg10):
    """Recheck the frozen admission before starting a new model process."""
    r=validate_resource_protocol(protocol)
    available=integer(available_bytes,'start MemAvailable')
    gpu_used=finite(gpu.get('used_mib'),'start GPU used MiB',0,r['gpu']['memory_total_mib'])
    gpu_temp=temp(gpu.get('temperature_c'),'start GPU temperature')
    cpu_temp=temp(thermal.get('cpu_tctl_c'),'start CPU Tctl')
    pressure=finite(psi_full_avg10,'start PSI full avg10',0,100)
    reasons=[]
    if available<r['cgroup']['memory_max_bytes']+r['memory']['reserve_bytes']:
        reasons.append('HOST_CAP_PLUS_RESERVE_UNAVAILABLE')
    if gpu.get('uuid')!=r['gpu']['uuid'] or gpu.get('bdf')!=r['gpu']['bdf']:
        reasons.append('GPU_IDENTITY')
    if gpu_used>=r['gpu']['memory_stop_total_mib']:reasons.append('GPU_TOTAL_MEMORY')
    if gpu_temp>=r['gpu']['temperature_stop_c']:reasons.append('GPU_TEMPERATURE_ADMISSION')
    if cpu_temp>=r['cpu']['temperature_stop_c']:reasons.append('CPU_TJMAX')
    if r['start']['initial_cpu_below_warning'] and cpu_temp>=r['cpu']['temperature_warning_c']:
        reasons.append('CPU_START_WARNING')
    if r['start']['initial_gpu_below_warning_when_available'] and \
       r['gpu']['temperature_warning_c'] is not None and \
       gpu_temp>=r['gpu']['temperature_warning_c']:
        reasons.append('GPU_START_WARNING')
    readings=thermal.get('nvme_composite_by_sensor')
    if type(readings) is not dict:raise ResourcePolicyError('start NVMe readings absent')
    for row in r['nvme']:
        value=temp(readings.get(row['sensor']),'start NVMe '+row['sensor'])
        if value>=row['stop_c']:reasons.append('NVME_TEMPERATURE_ADMISSION:'+row['sensor'])
        if r['start']['initial_nvme_below_warning_when_available'] and \
           row['warning_c'] is not None and value>=row['warning_c']:
            reasons.append('NVME_START_WARNING:'+row['sensor'])
    if power!=r['power']:reasons.append('POWER_CONDITION_CHANGED')
    if pressure>=r['memory']['psi_full_avg10_stop_percent']:
        reasons.append('HOST_PSI_AT_STOP')
    return reasons

def host_pressure():
    line=next((line for line in Path('/proc/pressure/memory').read_text().splitlines()
               if line.startswith('full ')),None)
    if line is None:raise ResourcePolicyError('host full PSI absent')
    fields=dict(part.split('=',1) for part in line.split()[1:])
    return finite(float(fields['avg10']),'host PSI full avg10',0,100)

def live_power():
    online=[]
    for item in sorted(Path('/sys/class/power_supply').iterdir()):
        kind=(item/'type').read_text().strip()
        if kind in ('Mains','USB','USB_C','USB_PD') and (item/'online').is_file() and \
           (item/'online').read_text().strip()=='1':
            online.append(item.name)
    profile=subprocess.check_output(['powerprofilesctl','get'],text=True,timeout=3).strip()
    return {'source':'AC' if online else 'BATTERY','online_sources':online,'profile':profile}

class RuntimeGuard:
    """Stateful prospective persistence gate; all comparisons are frozen."""
    def __init__(self,protocol,start_cgroup):
        self.r=validate_resource_protocol(protocol)
        self.start=start_cgroup
        self.low_samples=0
        self.reserve_since=None
        self.pressure_since=None

    def check(self,sample):
        r=self.r; t=finite(sample['elapsed_s'],'sample time',0)
        cg=sample['cgroup'];ps=sample['proc'];gpu=sample['gpu'];th=sample['thermal']
        obs=sample['resource_observation'];memory=sample['mem_available_bytes']
        for key in ('memory_max','swap_max','memory_current','memory_peak','swap_current'):
            integer(cg.get(key), 'cgroup '+key)
        for key in ('VmSwap','VmRSS','VmHWM'):
            integer(ps.get(key),'process '+key)
        finite(gpu.get('used_mib'),'GPU used MiB',0,r['gpu']['memory_total_mib'])
        temp(gpu.get('temperature_c'),'GPU runtime temperature')
        temp(th.get('cpu_tctl_c'),'CPU runtime Tctl')
        if cg['memory_max']!=r['cgroup']['memory_max_bytes'] or cg['swap_max']!=0 or \
           cg['path']!=self.start['path']:
            return 'CGROUP_IDENTITY_OR_CAP'
        if ps['VmSwap'] or cg['swap_current']:
            return 'WORKLOAD_SWAP'
        for kind in ('events','events_local'):
            if any(cg[kind][name]>self.start[kind][name] for name in ('max','oom','oom_kill')):
                return 'CGROUP_EVENT'
        if cg['memory_current']>=r['cgroup']['memory_stop_bytes'] or \
           cg['memory_peak']>=r['cgroup']['memory_stop_bytes']:
            return 'CGROUP_PREVENTIVE_MARGIN'
        if gpu['uuid']!=r['gpu']['uuid'] or gpu['bdf']!=r['gpu']['bdf']:
            return 'GPU_IDENTITY'
        if gpu['used_mib']>=r['gpu']['memory_stop_total_mib']:
            return 'GPU_TOTAL_MEMORY'
        if gpu['temperature_c']>=r['gpu']['temperature_stop_c']:
            return 'GPU_TEMPERATURE_ADMISSION'
        if th['cpu_tctl_c']>=r['cpu']['temperature_stop_c']:
            return 'CPU_TJMAX'
        for row in r['nvme']:
            value=th['nvme_composite_by_sensor'].get(row['sensor'])
            if value is None:return 'NVME_SENSOR_MISSING'
            if temp(value,'NVMe runtime')>=row['stop_c']:
                return 'NVME_TEMPERATURE_ADMISSION'
        power=obs['power']
        if power['source']!=r['power']['source'] or \
           power['profile']!=r['power']['profile'] or \
           power['online_sources']!=r['power']['online_sources']:
            return 'POWER_CONDITION_CHANGED'
        if type(memory) is not int or memory<0:return 'HOST_MEMORY_INVALID'
        self.low_samples=self.low_samples+1 if memory<r['memory']['available_stop_bytes'] else 0
        if self.low_samples>=r['memory']['available_stop_samples']:
            return 'HOST_MEMORY_1GIB_PERSISTED'
        self.reserve_since=(t if self.reserve_since is None else self.reserve_since) \
            if memory<r['memory']['reserve_bytes'] else None
        if self.reserve_since is not None and t-self.reserve_since>=r['memory']['reserve_stop_duration_s']:
            return 'HOST_RESERVE_PERSISTED'
        pressure=finite(obs['host_psi_full_avg10'],'PSI full avg10',0,100)
        self.pressure_since=(t if self.pressure_since is None else self.pressure_since) \
            if pressure>=r['memory']['psi_full_avg10_stop_percent'] else None
        if self.pressure_since is not None and t-self.pressure_since>=r['memory']['psi_stop_duration_s']:
            return 'HOST_PSI_PERSISTED'
        return None
