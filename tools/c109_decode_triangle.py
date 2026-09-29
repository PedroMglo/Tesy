#!/usr/bin/env python3
"""Frozen C35/C75 OFF/ON long-decode discriminator; original libraries only."""

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import time

import c2_server_run as server
from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol, live_power
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
from c100_server_wave_confirm import thermal_match

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'results/c109-decode-triangle-20260929T0815Z'
INPUT=ROOT/'raw/fixture_v2.ids.tsv'
CAP=18*GIB
BACKENDS={
    'A': (Path('/tmp/tesy-c35-backend-20260928'),
          'c3759bad92c0e6f71bb936afea9b0a162fb83f76',ROOT/'raw/c109_probe_c35'),
    'B': (Path('/tmp/tesy-c75-backend-20260928'),
          '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5',ROOT/'raw/c109_probe_c75'),
    'C': (Path('/tmp/tesy-c75-backend-20260928'),
          '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5',ROOT/'raw/c109_probe_c75'),
}
BLOCKS=(('A','B','C'),('B','C','A'),('C','A','B'))


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],text=True).strip()


def save_new(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')


def identity():
    out={}
    for arm,(backend,commit,binary) in BACKENDS.items():
        if arm=='C':
            continue
        if git('-C',backend,'rev-parse','HEAD')!=commit or \
           git('-C',backend,'status','--porcelain'):
            raise GateError('C109 backend identity/dirty state changed')
        out[arm]={'source_commit':commit,
                  'source_tree':git('-C',backend,'rev-parse','HEAD^{tree}'),
                  'binary_sha256':sha256(binary),
                  'mapped_libraries_expected':backend_library_hashes(str(binary),backend),
                  'compile_commands_sha256':sha256(next(backend.glob('build-*/compile_commands.json')))}
    out['C']=dict(out['B'])
    return out


def freeze():
    if (ROOT/'protocol.json').exists() or (ROOT/'preflight.json').exists():
        raise GateError('C109 no-replace freeze exists')
    snapshot=strict_json((ROOT/'snapshot.json').read_text())
    policy=strict_json((ROOT/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy or policy['memory']['cap_max_bytes']<CAP:
        raise GateError('C109 resource inventory not admissible')
    model_stat=file_identity(MODEL)
    if model_stat['size_bytes']!=63387346208:
        raise GateError('C109 canonical model size changed')
    if sha256(INPUT)!=sha256(ROOT/'raw/fixture_v2_c75.ids.tsv'):
        raise GateError('C109 official tokenizer outputs differ across backends')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP,
                                               start_mode='CAUSAL_AB_START')
    protocol={'schema':'c109-decode-triangle-v1','status':'FROZEN_BEFORE_INFERENCE',
              'objective':'separate C35/C75 compiled-source effect, wave flag effect and state dependence on a 2009+192 teacher-forced P12/8K decode',
              'alternative':'C100 decode regression is variance or session state; C104 short decode is not decisive',
              'input_sha256':sha256(INPUT),
              'input_generation':'embedded model chat template; synthetic SQLite technical conversation; 2009 prompt IDs and first 192 answer IDs, C35/C75 vocab-only tokens identical',
              'model_stat':model_stat,
              'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
              'backend_identity':identity(),
              'probe_source_sha256':sha256(REPO/'tools/c109_decode_triangle_probe.cpp'),
              'runner_source_sha256':sha256(__file__),
              'monitor_source_sha256':sha256(REPO/'tools/run_bounded.py'),
              'resources':resources,
              'profile':{'n_ctx':8192,'n_batch':256,'n_ubatch':32,'n_seq_max':1,
                         'n_threads':8,'n_threads_batch':8,'n_gpu_layers':12,'slots':32,
                         'io_threads':4,'preload':'ON','swa_full':True,
                         'kv_type':'F16','kv_unified':True,'kv_offload':True,
                         'flash_attention':True,'mmap':False,'direct_io':True,
                         'moe_stream_direct':True,'op_offload':False,
                         'template':'embedded GGUF template with synthetic system instruction medium',
                         'sampling':'teacher-forced; no free generation'},
              'call_plan':'2009 prompt IDs in external chunks of <=256; only final prompt output mask. Then 192 single-token teacher-forced calls, each completion-fenced with full 201088 F32 logits. All logits exported after phase timestamps.',
              'canary':{'arms':['A','B','C'],'prompt_ids':16,'continuation_ids':2,'timeout_s':120},
              'blocks':[list(block) for block in BLOCKS],
              'start':{'within_block_cpu_c':3,'gpu_c':3,'nvme_c':2,
                       'match_total_s_per_block':300,'inventory_s_per_block':60,
                       'thermal_regime':'cold matched within block; no global cache clearing'},
              'metrics':{'primary':'steps65_192_s','diagnostics':['prefill_s','steps1_64_s','steps1_77_s','steps_by_32','total_decode_s'],
                         'gain_formula':'100*(control-candidate)/control for B/A and C/B by block'},
              'decision_rule':{'B_A_late_loss':'B/A >5% loss in all three blocks, C/B does not reproduce: investigate compiled/build difference',
                               'C_B_early_only':'C/B diverges early then converges: state hypothesis, not isolated cause',
                               'C_B_late_loss':'C/B >5% loss in all three blocks: investigate indirect state/cache',
                               'mixed':'INCONCLUSIVE_ATTRIBUTION; no promotion'},
              'limits':{'timeout_s_per_arm':450,'max_model_arm_count':12,
                        'raw_new_bytes_max':40*GIB},
              'stop':'first identity, same-profile logits, nonfinite, output, resource, timeout or matched-start failure closes unit; no retry',
              'claim_limit':'probe attribution only, not server product TTFT or M4',
              'publication':'local commits only; no push/PR/default change'}
    validate_resource_protocol(protocol)
    save_new(ROOT/'protocol.json',protocol)
    save_new(ROOT/'preflight.json',{'schema':'c109-preflight-v1','utc':datetime.now(timezone.utc).isoformat(),
                                  'status':'FROZEN_NOT_MEASURED',
                                  'snapshot_sha256':sha256(ROOT/'snapshot.json'),
                                  'resource_policy_sha256':sha256(ROOT/'resource-policy.json'),
                                  'protocol_sha256':sha256(ROOT/'protocol.json'),
                                  'input_sha256':sha256(INPUT),
                                  'model_free_probe':'C35/C75 2009+192 PASS; malformed ID fixture rejected',
                                  'cgroup_cap_bytes':CAP})
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','protocol_sha256':sha256(ROOT/'protocol.json')}))


def observation():
    return {'thermal':server.thermal_state(prospective=True),
            'gpu':server.gpu_state(prospective=True),'power':live_power()}


def block_inventory(block):
    path=ROOT/'raw'/f'c109-block{block}-start-series.jsonl'
    started=time.monotonic()
    with path.open('x') as out:
        while True:
            no_other_model()
            observed=observation()
            elapsed=time.monotonic()-started
            out.write(json.dumps({'elapsed_s':elapsed,'observation':observed},allow_nan=False)+'\n')
            out.flush()
            if elapsed>=60:
                return {'observation':observed,'elapsed_s':elapsed,'sha256':sha256(path)}
            time.sleep(max(0,1-(time.monotonic()-started-elapsed)))


def match(anchor,block,order,p,remaining_s):
    path=ROOT/'raw'/f'c109-block{block}-order{order}-match.jsonl'
    sensor=p['resources']['nvme'][0]['sensor']
    started=time.monotonic()
    with path.open('x') as out:
        while True:
            no_other_model()
            current=observation()
            elapsed=time.monotonic()-started
            out.write(json.dumps({'elapsed_s':elapsed,'observation':current},allow_nan=False)+'\n')
            out.flush()
            if current['power']['source']!=anchor['power']['source'] or \
               current['power']['profile']!=anchor['power']['profile']:
                raise GateError('C109 power regime changed during matching')
            if thermal_match(anchor,current,sensor):
                return {'status':'MATCHED','wait_s':elapsed,'sha256':sha256(path)}
            if elapsed>=remaining_s:
                raise GateError('C109 matched-start 300s block budget exhausted')
            time.sleep(1)


def verify_output(stem,arm,canary,p,raw):
    backend,commit,binary=BACKENDS[arm]
    identity=p['backend_identity'][arm]
    env={'TESY_CPU_WAVE_SKIP_PARKED':'1'} if arm=='C' else {}
    if raw['returncode']!=0 or raw['stop_reason'] is not None or \
       raw['binary_sha256']!=identity['binary_sha256'] or \
       raw['backend_sha']!=commit or \
       raw['backend_libraries_sha256']!=identity['mapped_libraries_expected'] or \
       raw['mapped_backend_libraries_sha256']!=identity['mapped_libraries_expected'] or \
       raw['explicit_env']!=env or raw['resource_authority']!=p['resources'] or \
       raw['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
       raw['artifact_identity']['stat_at_end']!=p['model_stat']:
        raise GateError('C109 bounded identity/resource/exit invalid')
    for suffix,digest in raw['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:
            raise GateError('C109 bounded raw output hash changed')
    expected_rows=3 if canary else 193
    f32=Path(str(stem)+'.logits.f32')
    if f32.stat().st_size!=expected_rows*201088*4:
        raise GateError('C109 full logits byte count invalid')
    with Path(str(stem)+'.steps.tsv').open(newline='') as stream:
        reader=csv.DictReader(stream,delimiter='\t')
        if reader.fieldnames!=['step','position','token_id','completion_s']:
            raise GateError('C109 step schema invalid')
        steps=list(reader)
    if len(steps)!=(2 if canary else 192):
        raise GateError('C109 step count invalid')
    for i,row in enumerate(steps):
        if int(row['step'])!=i or int(row['position'])!=(16 if canary else 2009)+i or \
           not math.isfinite(float(row['completion_s'])) or float(row['completion_s'])<=0:
            raise GateError('C109 step position/time invalid')
    with Path(str(stem)+'.ops.tsv').open(newline='') as stream:
        ops=list(csv.DictReader(stream,delimiter='\t'))
    if len(ops)!=1 or ops[0]['arm']!=arm or int(ops[0]['logit_rows'])!=expected_rows:
        raise GateError('C109 operation row invalid')
    return {'logits_sha256':sha256(f32),'steps_sha256':sha256(Path(str(stem)+'.steps.tsv')),
            'ops_sha256':sha256(Path(str(stem)+'.ops.tsv')),
            'timing_s':{key:float(ops[0][key]) for key in
                        ('model_load_s','context_init_s','prefill_s','decode_s',
                         'step1_64_s','step65_192_s','step1_77_s')},
            'steps_s':[float(row['completion_s']) for row in steps]}


def launch(run_id,arm,canary,p,measurement_commit):
    backend,commit,binary=BACKENDS[arm]
    stem=ROOT/'raw'/run_id
    if Path(str(stem)+'.json').exists():
        raise GateError('C109 no-replace run already exists')
    no_other_model()
    if git('rev-parse','HEAD')!=measurement_commit or \
       file_identity(MODEL)!=p['model_stat'] or \
       sha256(binary)!=p['backend_identity'][arm]['binary_sha256']:
        raise GateError('C109 per-run measurement identity changed')
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
             '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
             '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
             '--backend','streaming','--backend-root',str(backend),
             '--output-root',str((ROOT/'raw').resolve()),
             '--variant',f'C109-{arm}'+('-canary' if canary else '-long-decode'),
             '--workload',str(INPUT),
             '--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
             '--timeout-s',str(120 if canary else 450),
             '--resource-protocol',str(ROOT/'protocol.json'),
             '--require-telemetry','--ready-marker','C109_READY']
    if arm=='C':command+=['--env','TESY_CPU_WAVE_SKIP_PARKED=1']
    command+=['--',str(binary),str(MODEL),str(INPUT),str(stem),'--arm',arm]
    if canary:command.append('--canary')
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    receipt={'schema':'c109-arm-receipt-v1','run_id':run_id,'arm':arm,
             'measurement_commit':measurement_commit,'scope_returncode':proc.returncode,
             'scope_stderr_tail':proc.stderr[-1000:],'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    mpath=Path(str(stem)+'.json')
    if mpath.is_file():
        raw=strict_json(mpath.read_text())
        receipt.update(manifest_sha256=sha256(mpath),returncode=raw.get('returncode'),
                       stop_reason=raw.get('stop_reason'),elapsed_s=raw.get('elapsed_s'),
                       maxima=raw.get('maxima'),start=raw.get('resource_start_observation'))
        if proc.returncode==0:
            try:
                receipt['source']=verify_output(stem,arm,canary,p,raw)
                receipt['status']='PASS_ARM'
            except (GateError,KeyError,ValueError,TypeError,OSError) as exc:
                receipt['reason']=f'{type(exc).__name__}: {exc}'
        else:receipt['reason']='scope/child nonzero; inspect bounded raw'
    else:receipt['reason']='bounded manifest absent'
    save_new(ROOT/'raw'/f'{run_id}-receipt.json',receipt)
    with (ROOT/'runs.jsonl').open('a') as stream:
        stream.write(json.dumps(receipt,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'run_id':run_id,'status':receipt['status'],
                      'timing_s':receipt.get('source',{}).get('timing_s'),
                      'reason':receipt.get('reason')}),flush=True)
    return receipt


def run(measurement_commit):
    os.chdir(REPO)
    p=strict_json((ROOT/'protocol.json').read_text())
    pre=strict_json((ROOT/'preflight.json').read_text())
    if git('rev-parse','HEAD')!=measurement_commit or \
       git('status','--porcelain') or relevant_environment(os.environ) or \
       pre['protocol_sha256']!=sha256(ROOT/'protocol.json') or \
       p['backend_identity']!=identity() or \
       p['input_sha256']!=sha256(INPUT) or \
       p['model_stat']!=file_identity(MODEL):
        raise GateError('C109 frozen measurement tree/environment invalid')
    validate_resource_protocol(p)
    (ROOT/'runs.jsonl').open('x').close()
    by_arm={}
    for arm in ('A','B','C'):
        receipt=launch(f'c109-canary-{arm.lower()}',arm,True,p,measurement_commit)
        if receipt['status']!='PASS_ARM':
            return 1
        by_arm[arm]=receipt
    if len({receipt['source']['logits_sha256'] for receipt in by_arm.values()})!=1:
        raise GateError('C109 canary same-profile full logits differ')
    prior={}
    for block,order in enumerate(BLOCKS,1):
        block_inventory(block)
        remaining_match_s=300.0
        anchor=None
        for position,arm in enumerate(order,1):
            if anchor is not None:
                matched=match(anchor,block,position,p,remaining_match_s)
                remaining_match_s-=matched['wait_s']
            run_id=f'c109-b{block}-{arm.lower()}'
            receipt=launch(run_id,arm,False,p,measurement_commit)
            if receipt['status']!='PASS_ARM':
                return 1
            if anchor is None:anchor=receipt['start']
            digest=receipt['source']['logits_sha256']
            if arm in prior and prior[arm]!=digest:
                raise GateError('C109 fresh-process same-arm full logits differ')
            prior[arm]=digest
        if len(set(prior.values()))!=1:
            raise GateError('C109 C35/C75/flag full logits differ in tested profile')
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    if args.action=='freeze':freeze()
    else:
        if not args.measurement_commit:parser.error('run requires measurement commit')
        raise SystemExit(run(args.measurement_commit))
