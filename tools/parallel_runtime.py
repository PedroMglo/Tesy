"""Optional prospective OpenMP environment/runtime identity and cheap CPU reads."""
import os
from pathlib import Path
from c2_gate import GateError
from run_bounded import sha256

PREFIXES=('OMP_','GOMP_','KMP_')
KNOWN=('OMP_WAIT_POLICY','OMP_NUM_THREADS','OMP_DYNAMIC','OMP_PROC_BIND','OMP_PLACES',
       'GOMP_SPINCOUNT','GOMP_CPU_AFFINITY','KMP_BLOCKTIME','KMP_AFFINITY')

def parallel_environment(env):
    values={k:v for k,v in env.items() if k.startswith(PREFIXES)}
    return {'values':values,'unset':[k for k in KNOWN if k not in env]}

def validate_launch_runtime(contract,env):
    if type(contract) is not dict or set(contract)!={'schema','environment','libraries_sha256'} or contract['schema']!='parallel-runtime-v1':
        raise GateError('parallel runtime schema invalid')
    if parallel_environment(env)!=contract['environment']:raise GateError('parallel environment changed')
    libs=contract['libraries_sha256']
    if type(libs) is not dict or len(libs)!=1:raise GateError('one pinned libgomp required')
    for p,h in libs.items():
        q=Path(p)
        if str(q.resolve())!=p or not q.name.startswith('libgomp') or sha256(q)!=h:raise GateError('parallel runtime library changed')
    return {'environment':parallel_environment(env),'expected_libraries_sha256':libs}

def mapped_parallel_runtime(pid,contract):
    found={}
    for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
        p=line.rsplit(' ',1)[-1]
        if p.startswith('/') and Path(p).name.startswith(('libgomp','libomp','libiomp')):
            q=Path(p).resolve();found[str(q)]=sha256(q)
    if found!=contract['libraries_sha256']:raise GateError('mapped parallel runtime differs')
    env={}
    for row in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
        if b'=' not in row:continue
        k,v=row.split(b'=',1);k=k.decode()
        if k.startswith(PREFIXES):env[k]=v.decode()
    if parallel_environment(env)!=contract['environment']:raise GateError('child parallel environment differs')
    return {'libraries_sha256':found,'initial_process_environment':parallel_environment(env),
            'source_note':'ggml init may set KMP_BLOCKTIME=200 after exec; GNU libgomp does not use KMP blocktime. /proc/environ observes initial exec environment.'}

def optional_cpu_observation():
    clocks={};unavailable=[]
    for p in sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy[0-9]*')):
        try:clocks[p.name]=int((p/'scaling_cur_freq').read_text())/1000
        except (OSError,ValueError):unavailable.append(p.name)
    energy=[]
    for p in Path('/sys/class/powercap').glob('*:0'):
        try:energy.append({'name':(p/'name').read_text().strip(),'energy_uj':int((p/'energy_uj').read_text()),'range_uj':int((p/'max_energy_range_uj').read_text())})
        except (OSError,ValueError):unavailable.append(str(p))
    return {'cpufreq_reported_current_mhz':clocks,'clock_semantics':'instantaneous driver-reported scaling_cur_freq, not effective instruction/compute clock',
            'package_energy':energy or 'UNKNOWN_UNAVAILABLE','unavailable':unavailable}
