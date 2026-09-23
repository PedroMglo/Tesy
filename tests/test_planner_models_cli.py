import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tesy import baseline, models
from tesy.io import ContractError
from tesy.planner import transport_bound

ROOT=Path(__file__).resolve().parents[1]


def contract(kind='ASSUMED'):
    return {'schema':'tesy.roofline.v1','minimum_tokens_per_second':{'numerator':3,'denominator':1},
            'tiers':[{'name':'h2d','bytes_per_committed_token':20_000_000_000,
                      'bandwidth_Bps':16_000_000_000,'bandwidth_kind':kind}]}


def test_measured_not_hard_bound():
    assert transport_bound(contract('MEASURED_REFERENCE'))['decision']=='ESTIMATED_INFEASIBLE'
    assert transport_bound(contract('UPPER_BOUND'))['decision']=='NOGO_HARD_TRANSPORT_BOUND'


def test_unknown_bandwidth_and_possible_not_pass():
    c=contract('UNKNOWN'); c['tiers'][0]['bandwidth_Bps']=None
    assert transport_bound(c)['decision']=='INCONCLUSIVE_MISSING_BANDWIDTH'
    c=contract(); c['tiers'][0]['bytes_per_committed_token']=1
    assert transport_bound(c)['decision']=='NOT_EXCLUDED_BY_TRANSPORT'
    assert transport_bound(c)['qualification'] is False


@pytest.mark.parametrize('value',[True,False,-1,0,1.2,'2',float('nan'),float('inf')])
def test_invalid_bandwidth(value):
    c=contract(); c['tiers'][0]['bandwidth_Bps']=value
    with pytest.raises(ContractError): transport_bound(c)


def test_duplicate_tier_and_keys():
    c=contract(); c['tiers']*=2
    with pytest.raises(ContractError): transport_bound(c)
    c=contract(); c['allowed_to_pass']=True
    with pytest.raises(ContractError): transport_bound(c)


def test_model_lock_and_download():
    m=models.get_model(ROOT/'configs/models.lock.json','qwen3-30b-a3b-2507-q4km')
    plan=models.download_plan(m,'/tmp/models with space')
    assert plan['downloads_performed'] is False and '*' not in ' '.join(plan['argv'])
    assert plan['argv'][3]==m['file'] and m['revision'] in plan['argv']
    assert len(m['revision'])==40 and len(m['sha256'])==64


def test_bad_model_size_stops_before_hash(tmp_path):
    m=models.get_model(ROOT/'configs/models.lock.json','qwen3-30b-a3b-2507-q4km')
    p=tmp_path/'x.gguf'; p.write_bytes(b'GGUF')
    with pytest.raises(ContractError,match='byte count'):
        models.verify(m,p)


def test_duplicate_model_id_and_path(tmp_path):
    raw=json.loads((ROOT/'configs/models.lock.json').read_text())
    raw['models']*=2
    p=tmp_path/'lock.json'; p.write_text(json.dumps(raw))
    with pytest.raises(ContractError): models.get_model(p,raw['models'][0]['id'])
    raw['models']=raw['models'][:1]; raw['models'][0]['file']='../evil.gguf'
    p.write_text(json.dumps(raw))
    with pytest.raises(ContractError): models.get_model(p,raw['models'][0]['id'])


def test_stock_command_is_shell_free_and_explicit():
    argv=baseline.command('/tmp/llama cli','/tmp/model;not-shell.gguf',False)
    assert argv[0]=='/tmp/llama cli' and argv[2]=='/tmp/model;not-shell.gguf'
    assert '--offline' in argv and '--cpu-moe' in argv and '--no-op-offload' in argv
    assert '--model-draft' not in argv and '-hf' not in argv
    assert '--cpu-moe' not in baseline.command('cli','model',True)


def healthy():
    return {'memory':{'MemAvailable_bytes':30*2**30,'SwapTotal_bytes':2**30,
                      'SwapFree_bytes':2**30,'cgroup_memory.max':None},
            'gpu':{'status':'OBSERVED','devices':[{'name':'RTX 4060 Laptop GPU',
                    'used_bytes':1*2**30,'total_bytes':8*2**30,'temperature_c':50}]}}


@pytest.mark.parametrize('what',['ram','swap','gpu','temp','missing','cgroup'])
def test_resource_guard(what):
    h=healthy()
    if what=='ram': h['memory']['MemAvailable_bytes']=1
    if what=='swap': h['memory']['SwapFree_bytes']=0
    if what=='gpu': h['gpu']['devices'][0]['used_bytes']=8*2**30
    if what=='temp': h['gpu']['devices'][0]['temperature_c']=99
    if what=='missing': h['gpu']['status']='NOT_AVAILABLE'
    if what=='cgroup': h['memory']['cgroup_memory.max']=1024
    with pytest.raises(ContractError): baseline.check_resources(h,0,False)


def cli(*args):
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
    return subprocess.run([sys.executable,'-m','tesy',*map(str,args)],cwd=ROOT,
                          capture_output=True,text=True,env=env,timeout=15)


@pytest.mark.parametrize('args',[
    ['doctor'], ['simulate','--trace','examples/routing.synthetic.json','--profile','examples/synthetic-profile.json'],
    ['union','--trace','examples/routing.synthetic.json','--k','4'],
    ['plan','--contract','examples/roofline.synthetic.json'],
    ['models','download-plan','--id','qwen3-30b-a3b-2507-q4km','/tmp/models'],
    ['chat','--model','/missing/model.gguf','--llama-cli','/missing/llama-cli'],
])
def test_cli_real_entrypoints(args):
    p=cli(*args)
    assert p.returncode==0,p.stderr
    assert type(json.loads(p.stdout)) is dict


def test_cli_no_replace_and_exit_code(tmp_path):
    out=tmp_path/'doctor.json'
    assert cli('doctor','--output',out).returncode==0
    assert cli('doctor','--output',out).returncode==2
    assert cli('union','--trace','examples/routing.synthetic.json','--k','0').returncode==2
