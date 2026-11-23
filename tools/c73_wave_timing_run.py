#!/usr/bin/env python3
"""Contemporary P12 wave OFF/ON probe for cold513 and retained-KV incremental154."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess

from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
from c66_wave_id_diagnostic import BACKEND

REPO = Path(__file__).resolve().parents[1]
INPUT_SOURCE = REPO/'results/c52b-assistant-history-sustained-20260928T1132Z/raw/c52b-p12-assistant-history01.tokenization.json'
INPUT_MANIFEST = REPO/'results/c52b-assistant-history-sustained-20260928T1132Z/manifest.json'
NUMERIC = REPO/'results/c2-target-numeric-v1.ids'
BINARY = REPO/'tools/c73_wave_probe'
CAP = 18*GIB
CASES = {'cold513': 513, 'warm154': 154}
ARMS = (('cold513', 1, 'off'), ('cold513', 1, 'on'),
        ('cold513', 2, 'on'), ('cold513', 2, 'off'),
        ('warm154', 1, 'off'), ('warm154', 1, 'on'),
        ('warm154', 2, 'on'), ('warm154', 2, 'off'))
VOCAB = 201088

def git(*args):
    return subprocess.check_output(['git', *map(str,args)], text=True).strip()

def save_new(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')

def run_id(case, pair, wave):
    return f'c73-{case}-p{pair}-wave-{wave}'

def ids(root):
    evidence = strict_json(INPUT_MANIFEST.read_text())['raw_sha256'][INPUT_SOURCE.name]
    if sha256(INPUT_SOURCE) != evidence['sha256'] or INPUT_SOURCE.stat().st_size != evidence['size_bytes']:
        raise GateError('C52b tokenization source hash changed')
    original = strict_json(INPUT_SOURCE.read_text())
    a,b = original['c52b-turn00'],original['c52b-turn01']
    numeric = next((line.split('\t') for line in NUMERIC.read_text().splitlines()
                    if line.startswith('log_medium\t')), None)
    if not numeric or len(numeric) != 3 or len(a)!=2043 or len(b)!=2197 or b[:2043]!=a:
        raise GateError('C73 source tokenization shape changed')
    continuation = list(map(int,numeric[2].split(',')))[:32]
    expected = [('cold513',a[:513]),('warm_prefix2043',a),
                ('warm_tail154',b[2043:]),('continuation32',continuation)]
    parsed = [(row[0],list(map(int,row[1].split(','))))
              for row in (line.split('\t') for line in (root/'input.tsv').read_text().splitlines())]
    if parsed!=expected or len(continuation)!=32:
        raise GateError('C73 frozen input differs from C52b/numeric source')
    return dict(expected)

def protocol(root):
    gates = [('c70-full-wave-boundary-20260928T1652Z','SAME_PROFILE_BITWISE_PASS_FULL_BOUNDARY'),
             ('c71-wave-reference-20260928T1659Z','PASS_FULL_RESIDENT_CANONICAL_FFN_TESTED_SCOPE'),
             ('c72-wave-repeat-20260928T1705Z','SAME_PROFILE_BITWISE_PASS_FRESH_PROCESS_REPEAT')]
    gate_hashes = {}
    for name,status in gates:
        path=REPO/'results'/name/'decision.json'
        if strict_json(path.read_text())['status']!=status:
            raise GateError('C73 numerical prerequisite changed: '+name)
        gate_hashes[name]=sha256(path)
    if git('-C', BACKEND, 'rev-parse', 'HEAD') != '1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22' or \
       git('-C', BACKEND, 'status', '--porcelain'):
        raise GateError('C66 backend source changed')
    snapshot = strict_json((root/'snapshot.json').read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot) != policy:
        raise GateError('fresh resource policy changed')
    stat = file_identity(MODEL)
    if any(stat[key] != snapshot['model_stat'][key] for key in
           ('dev','inode','size_bytes','mtime_ns')):
        raise GateError('verified canonical model stat changed')
    input_ids = ids(root)
    libs = backend_library_hashes(str(BINARY), BACKEND)
    if not libs:
        raise GateError('probe libraries absent')
    resources = freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    out = {'schema':'c73-p12-wave-timing-screen-v1','campaign_id':root.name,
           'hypothesis':'C57 skips parked CPU MMID and reduces completion-fenced prefill+32-step time on cold513 or retained-KV incremental154',
           'alternative':'parked MMID is overlapped with I/O/other work, so skipping it does not reduce full-model elapsed time',
           'backend_sha':git('-C',BACKEND,'rev-parse','HEAD'),
           'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
           'binary_sha256':sha256(BINARY),'binary_path':str(BINARY),
           'source_sha256':sha256(REPO/'tools/c73_wave_probe.cpp'),
           'runner_sha256':sha256(__file__),
           'numeric_gate_decision_sha256':gate_hashes,
           'monitor_sha256':sha256(REPO/'tools/run_bounded.py'),
           'backend_libraries_sha256':libs,
           'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
           'model_stat':stat,'numeric_ids_sha256':sha256(NUMERIC),
           'C52b_tokenization_sha256':sha256(INPUT_SOURCE),
           'input_tsv_sha256':sha256(root/'input.tsv'),
           'input_counts':{key:len(value) for key,value in input_ids.items()},
           'profile_common':{'n_ctx':4096,'n_batch':256,'n_ubatch':32,'slots':32,
                             'moe_stream':True,'preload':'OFF','swa_full':True,
                             'kv_unified':False,'kv_offload':True,'kv_type':'F16',
                             'flash_attention':True,'threads':8,'io_threads':4,
                             'mmap':False,'direct_io':True,'op_offload':False},
           'delta':{'TESY_CPU_WAVE_SKIP_PARKED':['unset','1']},'resources':resources,
           'arms':[{'run_id':run_id(case,pair,wave),'case':case,'pair':pair,'wave':wave,
                    'order':i+1} for i,(case,pair,wave) in enumerate(ARMS)],
           'metric':'T_work = completion-fenced prefill + 32 teacher-forced steps; load excluded',
           'gain_formula':'100*(wave_OFF_i-wave_ON_i)/wave_OFF_i',
           'decision':{'each_case_screen':{'median_work_gain_min_percent':5,
                                          'all_pair_work_gain_positive':True,
                                          'median_prefill_gain_min_percent':-5,
                                          'median_decode_gain_min_percent':-5}},
           'limits':{'timeout_cold513_s':600,'timeout_warm154_s':900,
                     'max_new_raw_bytes':40*GIB},
           'cache_condition':'fresh expert pools per arm; page cache uncontrolled; warm154 has retained KV after unmeasured 2043-ID conditioning, no exact-prefix server claim',
           'stop':'first resource, identity, output or within-profile repeatability failure; no retry',
           'claim_limit':'synthetic teacher-forced probe, not API TTFT, server cache or quality; new 513/154 shapes require observed same-profile full-logit equality',
           'publication':'local only; raw untracked'}
    validate_resource_protocol(out)
    return out

def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new root/raw required')
    p = protocol(root)
    save_new(root/'protocol.json',p)
    save_new(root/'preflight.json',{'schema':'c73-preflight-v1','utc':datetime.now(timezone.utc).isoformat(),
             'status':'FROZEN_NOT_MEASURED','protocol_sha256':sha256(root/'protocol.json'),
             'snapshot_sha256':sha256(root/'snapshot.json'),
             'resource_policy_sha256':sha256(root/'resource-policy.json'),
             'cgroup_cap_bytes':CAP})
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','root':str(root)}),flush=True)

def tsv(path,header):
    with path.open(newline='') as source:
        reader=csv.DictReader(source,delimiter='\t')
        if reader.fieldnames!=header: raise GateError('probe output header changed: '+path.name)
        return list(reader)

def arm_source(root,arm,p):
    run=arm['run_id']; stem=root/'raw'/run
    mpath=Path(str(stem)+'.json')
    m=strict_json(mpath.read_text())
    expected_cmd=[str(BINARY),str(MODEL),str(root/'input.tsv'),str(stem),
                  '--ngl','12','--case',arm['case']]
    env={'LLAMA_MOE_STREAM_NO_PRELOAD':'1'}
    if arm['wave']=='on':env['TESY_CPU_WAVE_SKIP_PARKED']='1'
    if m['run_id']!=run or m['variant']!=f'P12-wave-{arm["wave"]}-timing' or \
       m['command']!=expected_cmd or m['workload_sha256']!=p['input_tsv_sha256'] or \
       m['binary_sha256']!=p['binary_sha256'] or m['backend_sha']!=p['backend_sha'] or \
       m['backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       not m['mapped_libraries_match_ldd'] or m['explicit_env']!=env or \
       m['resource_authority']!=p['resources'] or \
       m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
       m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
       m['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json') or \
       m['returncode']!=0 or m['stop_reason'] is not None:
        raise GateError('run provenance/completion differs from freeze: '+run)
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:
            raise GateError('bounded raw hash changed: '+run+suffix)
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):dev for i,dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    first_gpu=25
    if set(placement)!=set(range(37)) or any(
       placement[i]!=('CPU' if i<first_gpu else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('loader placement/direct I/O changed: '+run)
    input_ids=ids(root)
    actual=input_ids['cold513' if arm['case']=='cold513' else 'warm_tail154']
    base=0 if arm['case']=='cold513' else 2043
    continuation=input_ids['continuation32']
    expected_rows=[{'phase':'prefill','position':str(base+len(actual)-1),'row':'0',
                    'token_id':str(actual[-1])}]
    expected_rows += [{'phase':'decode','position':str(base+len(actual)+i),
                       'row':str(i+1),'token_id':str(continuation[i])} for i in range(32)]
    if tsv(Path(str(stem)+'.rows.tsv'),['phase','position','row','token_id'])!=expected_rows:
        raise GateError('output mask/position/token IDs changed: '+run)
    chunk_rows=tsv(Path(str(stem)+'.chunks.tsv'),['chunk','start','count','dispatch_s'])
    if [(int(x['chunk']),int(x['start']),int(x['count'])) for x in chunk_rows]!=[
        (i,i*256,min(256,len(actual)-i*256)) for i in range((len(actual)+255)//256)]:
        raise GateError('external prefill chunk shape changed: '+run)
    if any(not math.isfinite(float(x['dispatch_s'])) or float(x['dispatch_s'])<=0
           for x in chunk_rows):raise GateError('invalid chunk timing')
    step_rows=tsv(Path(str(stem)+'.steps.tsv'),['step','token_id','completion_s'])
    if [(int(x['step']),int(x['token_id'])) for x in step_rows]!=list(enumerate(continuation)):
        raise GateError('teacher-forced step sequence changed: '+run)
    steps=[float(x['completion_s']) for x in step_rows]
    if any(not math.isfinite(x) or x<=0 for x in steps):raise GateError('invalid step timing')
    op=tsv(Path(str(stem)+'.ops.tsv'),['ngl','case','conditioning_s',
        'model_load_s','context_init_s','prefill_completion_s','work_s','output_rows'])
    if len(op)!=1 or [op[0][k] for k in ('ngl','case','output_rows')]!=[
        '12',arm['case'],'33']:
        raise GateError('timing operation schema changed: '+run)
    vals={key:float(op[0][key]) for key in
          ('conditioning_s','model_load_s','context_init_s','prefill_completion_s','work_s')}
    if any(not math.isfinite(v) or v<=0 for k,v in vals.items() if k!='conditioning_s') or \
       not math.isfinite(vals['conditioning_s']) or \
       (arm['case']=='cold513' and vals['conditioning_s']!=0) or \
       (arm['case']=='warm154' and vals['conditioning_s']<=0) or \
       abs(vals['work_s']-vals['prefill_completion_s']-sum(steps))>0.0001:
        raise GateError('completion timing inconsistent: '+run)
    fpath=Path(str(stem)+'.f32')
    payload=fpath.read_bytes()
    if len(payload)!=33*VOCAB*4 or any(not math.isfinite(x[0]) for x in struct.iter_unpack('<f',payload)):
        raise GateError('full logits incomplete/nonfinite: '+run)
    output_hashes={suffix:sha256(Path(str(stem)+suffix)) for suffix in
                   ('.f32','.rows.tsv','.chunks.tsv','.steps.tsv','.ops.tsv')}
    return {'manifest_sha256':sha256(mpath),'elapsed_s':m['elapsed_s'],
            'maxima':m['maxima'],'placement':placement,'output_sha256':output_hashes,
            'timing_s':{'load_init':vals['model_load_s']+vals['context_init_s'],
                        'conditioning':vals['conditioning_s'],
                        'prefill':vals['prefill_completion_s'],'decode32':sum(steps),
                        'work':vals['work_s'],
                        'cold_e2e':vals['model_load_s']+vals['context_init_s']+
                                   vals['conditioning_s']+vals['work_s']},
            'step_s':steps}

def gains(root,p,receipts):
    by_id={r['run_id']:r for r in receipts}
    for case in CASES:
        for wave in ('off','on'):
            a,b=(root/'raw'/run_id(case,i,wave) for i in (1,2))
            if sha256(Path(str(a)+'.f32'))!=sha256(Path(str(b)+'.f32')):
                raise GateError(f'FAIL_SAME_PROFILE_FIDELITY {case} wave {wave} full33')
        for pair in (1,2):
            a,b=(root/'raw'/run_id(case,pair,wave) for wave in ('off','on'))
            if sha256(Path(str(a)+'.f32'))!=sha256(Path(str(b)+'.f32')):
                raise GateError(f'FAIL_SAME_PROFILE_FIDELITY {case} pair{pair} OFF/ON full33')
    report={'schema':'c73-timing-screen-v1','pairs':{},'decision_by_case':{}}
    for case in CASES:
        entries=[]
        for pair in (1,2):
            left=by_id[run_id(case,pair,'off')]['source']['timing_s']
            right=by_id[run_id(case,pair,'on')]['source']['timing_s']
            gain={metric:100*(left[metric]-right[metric])/left[metric]
                  for metric in ('work','prefill','decode32')}
            entries.append({'pair':pair,'OFF_s':left,'ON_s':right,'gain_percent':gain})
        report['pairs'][case]=entries
        med={metric:sum(sorted(x['gain_percent'][metric] for x in entries))/2
             for metric in ('work','prefill','decode32')}
        state='SCREEN_GO_CONFIRMATION_PENDING' if med['work']>=5 and all(
            x['gain_percent']['work']>0 for x in entries) and \
            med['prefill']>=-5 and med['decode32']>=-5 else 'NO_GO_SCREEN'
        report['decision_by_case'][case]={'status':state,'median_pair_gain_percent':med}
    return report

def run(root,commit):
    os.chdir(REPO)
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or relevant_environment(os.environ):
        raise GateError('measurement tree/environment changed')
    p=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if protocol(root)!=p or sha256(root/'protocol.json')!=pre['protocol_sha256'] or \
       sha256(root/'snapshot.json')!=pre['snapshot_sha256']:
        raise GateError('frozen protocol/inventory changed')
    receipts=[]
    for arm in p['arms']:
        if git('rev-parse','HEAD')!=commit or git('status','--porcelain') or \
           file_identity(MODEL)!=p['model_stat'] or sha256(BINARY)!=p['binary_sha256']:
            raise GateError('per-arm source/model/binary changed')
        no_other_model()
        run=arm['run_id'];stem=root/'raw'/run
        if any(Path(str(stem)+suffix).exists() for suffix in ('.json','.f32','.ops.tsv')):
            raise GateError('no-replace run exists: '+run)
        timeout=p['limits']['timeout_cold513_s' if arm['case']=='cold513' else 'timeout_warm154_s']
        command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
                 '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
                 '--run-id',run,'--model-id','gpt-oss-120b-mxfp4-gguf',
                 '--backend','streaming','--backend-root',str(BACKEND),
                 '--output-root',str((root/'raw').resolve()),
                 '--variant',f'P12-wave-{arm["wave"]}-timing','--workload',str(root/'input.tsv'),
                 '--cache-condition',p['cache_condition'],
                 '--timeout-s',str(timeout),'--resource-protocol',str(root/'protocol.json'),
                 '--require-telemetry','--ready-marker','C73_CONTEXT_READY',
                 '--env','LLAMA_MOE_STREAM_NO_PRELOAD=1']
        if arm['wave']=='on':command+=['--env','TESY_CPU_WAVE_SKIP_PARKED=1']
        command+=['--',str(BINARY),str(MODEL),str(root/'input.tsv'),str(stem),
                  '--ngl','12','--case',arm['case']]
        proc=subprocess.run(command,capture_output=True,text=True,check=False)
        receipt={'schema':'c73-arm-receipt-v1','run_id':run,'measurement_commit':commit,
                 'scope_returncode':proc.returncode,'scope_stderr_tail':proc.stderr[-1000:],
                 'status':'FAIL_RESOURCES_OR_EVIDENCE'}
        mpath=Path(str(stem)+'.json')
        if mpath.is_file():
            m=strict_json(mpath.read_text())
            receipt.update(returncode=m.get('returncode'),stop_reason=m.get('stop_reason'),
                           elapsed_s=m.get('elapsed_s'),maxima=m.get('maxima'))
            if proc.returncode==0:
                try:
                    receipt['source']=arm_source(root,arm,p)
                    receipt['status']='PASS_ARM'
                except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                    receipt['reason']=f'{type(exc).__name__}: {exc}'
            else:receipt['reason']='scope/child nonzero; inspect bounded stderr'
        else:receipt['reason']='bounded manifest absent'
        receipts.append(receipt)
        save_new(root/'raw'/(run+'-receipt.json'),receipt)
        print(json.dumps({'run_id':run,'status':receipt['status'],
                          'timing':receipt.get('source',{}).get('timing_s'),
                          'reason':receipt.get('reason')}),flush=True)
        if receipt['status']!='PASS_ARM':break
    with (root/'runs.jsonl').open('x') as out:
        for r in receipts:out.write(json.dumps(r,allow_nan=False,sort_keys=True)+'\n')
    if len(receipts)==len(ARMS):
        try:
            report=gains(root,p,receipts)
        except (GateError,ValueError,TypeError,OSError) as exc:
            report={'schema':'c73-timing-screen-v1','status':'FAIL_SAME_PROFILE_FIDELITY',
                    'reason':str(exc)}
    else:
        report={'schema':'c73-timing-screen-v1','status':'FAIL_RESOURCES_OR_EVIDENCE',
                'reason':'arm failed; no remaining runs executed'}
    save_new(root/'timing-pairs.json',report)
    return 0 if 'pairs' in report else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.action=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))
