#!/usr/bin/env python3
"""Prospective 44-slot numeric boundary and resident FFN reference under E20."""

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import subprocess

import c127_slots40_numeric as prior
from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from c66_wave_id_diagnostic import IDS
from host_resource_policy import GIB, derive_policy, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
from c70_full_boundary_gate import inspect
from c94_session_wave_8k_reference import validate_result, tree_digest


REPO = Path(__file__).resolve().parents[1]
ROOT_NAME = 'c137-slots44-numeric-20260929T2217Z'
BACKEND = Path('/tmp/tesy-c75-backend-20260928')
BACKEND_SHA = '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5'
CAP = 20 * GIB
RUNS = {'off':'c137-slots44-off01','on':'c137-slots44-on01'}
REFERENCE = Path('/tmp/c77_layer_reference')
ORIGINAL = REPO/'tools/c127_slots40_boundary_capture.cpp'
PRIOR = REPO/'results/c136-slots40-trace-neutral-20260929T2205Z/epoch-checkpoint.json'
OLD_COMMAND = prior.capture_command


def configure():
    prior.ROOT_NAME = ROOT_NAME
    prior.CAP = CAP
    prior.RUNS = RUNS
    prior.expected = expected
    prior.budget = budget
    prior.capture_command = capture_command
    prior.verify_capture = verify_capture


def generated_source():
    src = ORIGINAL.read_text()
    a,b = 'constexpr int slot_count = 40;', 'mp.moe_stream_slots = 40;'
    if src.count(a) != 1 or src.count(b) != 1:
        raise GateError('C127 numeric source transform no longer unique')
    return src.replace(a,'constexpr int slot_count = 44;').replace(b,'mp.moe_stream_slots = 44;')


def build(root):
    if prior.git('-C',BACKEND,'rev-parse','HEAD') != BACKEND_SHA or \
       prior.git('-C',BACKEND,'status','--porcelain'):
        raise GateError('C137 backend source changed')
    source = root/'build/c137_slots44_boundary_capture.cpp'
    binary = root/'build/c137_slots44_boundary_capture'
    if source.exists() or binary.exists():
        raise GateError('C137 build identity already used')
    source.write_text(generated_source())
    lib = BACKEND/'build-c75-cuda/bin'
    cmd = ['g++-15','-std=c++17','-O2','-Wall','-Wextra','-Werror',
        '-I',str(BACKEND/'include'),'-I',str(BACKEND/'src'),
        '-I',str(BACKEND/'ggml/include'),str(source),
        str(lib/'libllama.so'),str(lib/'libggml.so'),str(lib/'libggml-base.so'),
        f'-Wl,-rpath,{lib}','-ldl','-o',str(binary)]
    proc=subprocess.run(cmd,text=True,capture_output=True)
    if proc.returncode or not binary.is_file():
        raise GateError('C137 numeric build failed: '+proc.stderr[-1200:])
    return {'schema':'c137-build-v1','generated_source_sha256':sha256(source),
            'original_source_sha256':sha256(ORIGINAL),'binary_sha256':sha256(binary),
            'compiler_command':cmd,'backend_sha':BACKEND_SHA}


def budget():
    old=strict_json(PRIOR.read_text());now=datetime.now(timezone.utc)
    wall=(datetime.fromisoformat('2026-09-29T13:31:15+00:00')+
          timedelta(hours=12)-now).total_seconds()
    physical=old['physical_remaining_lower_bound_s']
    reserve=60+2*180+36*30+600
    if min(wall,physical)<reserve:
        raise GateError('C137 boundary/reference and closure reserve not admitted')
    return {'schema':'c137-budget-v1','utc':now.isoformat(),
            'prior_checkpoint_sha256':sha256(PRIOR),
            'physical_remaining_lower_bound_s':physical,'wall_remaining_s':wall,
            'reserved_s':reserve,'capture_timeout_s':180,'reference_timeout_s_per_layer':30}


def expected(root):
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy or policy['memory']['cap_max_bytes']<CAP:
        raise GateError('C137 physical inventory does not admit E20')
    stat=file_identity(MODEL)
    if any(stat[k]!=snapshot['model_stat'][k] for k in ('dev','inode','size_bytes','mtime_ns')):
        raise GateError('C137 model stat changed')
    if prior.git('-C',BACKEND,'rev-parse','HEAD')!=BACKEND_SHA or \
       prior.git('-C',BACKEND,'status','--porcelain'):
        raise GateError('C137 backend changed')
    source=root/'build/c137_slots44_boundary_capture.cpp'
    binary=root/'build/c137_slots44_boundary_capture'
    if source.read_text()!=generated_source() or not binary.is_file() or not REFERENCE.is_file():
        raise GateError('C137 generated source/binary/reference absent')
    libraries=backend_library_hashes(str(binary),BACKEND)
    if not libraries or libraries!=backend_library_hashes(str(REFERENCE),BACKEND):
        raise GateError('C137 backend libraries/reference differ')
    old=strict_json((REPO/'results/c80-session-numeric-source-20260928T1940Z/protocol.json').read_text())
    profile=dict(old['profile']);profile['slots']=44
    p={'schema':'c137-slots44-numeric-v1','campaign_id':root.name,
       'hypothesis':'Four additional slots reduce residual expert misses and decode waits under a physically admitted E20 profile',
       'alternative':'VRAM/RAM or numerical fidelity fails, or added slots cannot improve useful latency',
       'claim':'189+32 P12/8K short boundary and 36 resident FFN layers; full 8K attention/KV independent NOT_RUN',
       'model_stat':stat,'model_sha256_previously_verified':old['model_sha256_previously_verified'],
       'backend_sha':BACKEND_SHA,'backend_tree':prior.git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
       'binary_sha256':sha256(binary),'binary_path':str(binary),
       'backend_libraries_sha256':libraries,'generated_source_sha256':sha256(source),
       'original_source_sha256':sha256(ORIGINAL),
       'source_transform':'exact two replacements 40->44: slot_count and moe_stream_slots',
       'reference_binary_sha256':sha256(REFERENCE),'reference_binary_path':str(REFERENCE),
       'reference_source_sha256':sha256(REPO/'tools/c7_layer_reference.cpp'),
       'reference_gate_sha256':sha256(REPO/'tools/c94_session_wave_8k_reference.py'),
       'runner_sha256':sha256(__file__),'boundary_gate_sha256':sha256(REPO/'tools/c70_full_boundary_gate.py'),
       'numeric_ids_sha256':sha256(IDS),'profile':profile,'call_plan':old['call_plan'],
       'resources':freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP),
       'limits':{'capture_timeout_s':180,'reference_timeout_s_per_layer':30,
                 'raw_limit_bytes':512*2**20},'run_ids':RUNS,
       'numeric_gate':'OFF/ON bitwise active states/full logits then 36 canonical resident FFN layers; mismatch/stop closes unit',
       'default_changed':False,'publication':'LOCAL_ONLY'}
    validate_resource_protocol(p)
    return p


def capture_command(root,p,arm):
    cmd=OLD_COMMAND(root,p,arm)
    i=cmd.index('--variant')+1
    if cmd[i]!=f'P12-C127-slots40-{arm}':raise GateError('C137 inherited variant changed')
    cmd[i]=f'P12-C137-slots44-{arm}'
    j=cmd.index('--timeout-s')+1
    if cmd[j]!='600':raise GateError('C137 inherited capture timeout changed')
    cmd[j]='180'
    return cmd


def verify_capture(root,p,arm):
    stem=root/'raw'/RUNS[arm]
    manifest=Path(str(stem)+'.json')
    m=strict_json(manifest.read_text())
    env={'TESY_CPU_WAVE_SKIP_PARKED':'1'} if arm=='on' else {}
    if m['run_id']!=RUNS[arm] or m['variant']!=f'P12-C137-slots44-{arm}' or \
       m['binary_sha256']!=p['binary_sha256'] or m['backend_sha']!=BACKEND_SHA or \
       m['backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
       m['explicit_env']!=env or m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
       m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
       m['workload_sha256']!=p['numeric_ids_sha256'] or m['resource_authority']!=p['resources'] or \
       m['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json') or \
       m['returncode']!=0 or m['stop_reason'] is not None:
        raise GateError('C137 capture provenance/completion invalid')
    for suffix,digest in m['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:
            raise GateError('C137 capture raw hash mismatch')
    stderr=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):dev for i,dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',stderr)}
    if set(placement)!=set(range(37)) or \
       any(placement[i]!=('CPU' if i<25 else 'CUDA0') for i in placement) or \
       'MoE expert streaming uses O_DIRECT' not in stderr:
        raise GateError('C137 placement or direct I/O changed')
    observed=inspect(Path(str(stem)+'.capture'),skip_on=arm=='on')
    return {'status':'PASS_CAPTURE_ARM','manifest_sha256':sha256(manifest),
            'coverage':observed['coverage'],'sentinels':observed['sentinels'],
            'elapsed_s':m['elapsed_s'],'maxima':m['maxima']}


def reference(root,commit):
    p=prior.frozen(root,commit)
    on=strict_json((root/'raw'/f'{RUNS["on"]}-receipt.json').read_text())
    boundary=strict_json((root/'boundary-summary.json').read_text())
    if on['status']!='PASS_SAME_PROFILE_BOUNDARY' or boundary['status']!='SAME_PROFILE_BITWISE_PASS':
        raise GateError('C137 boundary prerequisite absent')
    capture=root/'raw'/(RUNS['on']+'.capture')
    digest=tree_digest(capture)
    receipts=[]
    for layer in range(36):
        no_other_model()
        run_id=f'c137-ref-l{layer:02d}-01';stem=root/'raw'/run_id
        cmd=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
             '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
             '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
             '--backend','streaming','--backend-root',str(BACKEND),
             '--output-root',str((root/'raw').resolve()),
             '--variant',f'P12-C137-slots44-canonical-layer{layer}',
             '--workload',str(capture/'index.tsv'),
             '--cache-condition','resident-canonical-one-layer-page-cache-uncontrolled',
             '--timeout-s','30','--resource-protocol',str(root/'protocol.json'),
             '--require-telemetry','--',p['reference_binary_path'],str(MODEL),
             str(capture),str(layer),'--ngl','12']
        proc=subprocess.run(cmd,capture_output=True,text=True,check=False,cwd=REPO)
        receipt={'schema':'c137-reference-receipt-v1','run_id':run_id,'layer':layer,
                 'measurement_commit':commit,'capture_tree':digest,
                 'scope_returncode':proc.returncode,'scope_stderr_tail':proc.stderr[-1000:],
                 'status':'FAIL_RESOURCES_OR_EVIDENCE'}
        try:
            if proc.returncode:raise GateError('C137 reference scope failed')
            path=Path(str(stem)+'.json');m=strict_json(path.read_text())
            if m['returncode']!=0 or m['stop_reason'] is not None or \
               m['variant']!=f'P12-C137-slots44-canonical-layer{layer}' or \
               m['binary_sha256']!=p['reference_binary_sha256'] or \
               m['backend_sha']!=BACKEND_SHA or \
               m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
               m['artifact_identity']['stat_at_launch']!=p['model_stat'] or \
               m['artifact_identity']['stat_at_end']!=p['model_stat'] or \
               m['workload_sha256']!=sha256(capture/'index.tsv') or \
               m['resource_authority']!=p['resources']:
                raise GateError('C137 reference identity invalid')
            if any(sha256(Path(str(stem)+suffix))!=h for suffix,h in m['output_sha256'].items()):
                raise GateError('C137 reference raw hash mismatch')
            value=strict_json(Path(str(stem)+'.stdout').read_text())
            if not validate_result(value,layer):raise GateError('C137 FFN/router mismatch')
            receipt.update(status='PASS_CANONICAL_LAYER',elapsed_s=m['elapsed_s'],
                           raw_manifest_sha256=sha256(path),
                           reference_sha256=sha256(Path(str(stem)+'.stdout')),
                           numeric_rows=value['numeric_rows'],masked_rows=value['masked_rows'])
        except Exception as exc:
            receipt.update(status='FAIL_SAME_PROFILE_OR_EVIDENCE' if proc.returncode==0 else
                           'FAIL_RESOURCES_OR_EVIDENCE',reason=f'{type(exc).__name__}: {exc}')
        prior.save_new(root/f'{run_id}-receipt.json',receipt)
        receipts.append(receipt)
        print(json.dumps({'layer':layer,'status':receipt['status'],
                          'reason':receipt.get('reason')},allow_nan=False),flush=True)
        if receipt['status']!='PASS_CANONICAL_LAYER':break
    status='PASS_FULL_REFERENCE' if len(receipts)==36 and all(
        x['status']=='PASS_CANONICAL_LAYER' for x in receipts) else 'FAIL_SAME_PROFILE_OR_EVIDENCE'
    prior.save_new(root/'reference-summary.json',{'schema':'c137-reference-summary-v1',
        'status':status,'measurement_commit':commit,'capture_tree':digest,
        'layers':[x['layer'] for x in receipts],
        'numeric_rows':sum(x.get('numeric_rows',0) for x in receipts),
        'masked_rows':sum(x.get('masked_rows',0) for x in receipts)})
    return 0 if status=='PASS_FULL_REFERENCE' else 1


if __name__=='__main__':
    configure()
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=('build','freeze','off','on','reference'))
    ap.add_argument('root',type=Path)
    ap.add_argument('--measurement-commit')
    args=ap.parse_args();root=args.root.resolve()
    if args.mode=='build':
        print(json.dumps(build(root),sort_keys=True));raise SystemExit(0)
    if args.mode=='freeze':prior.freeze(root);raise SystemExit(0)
    if not args.measurement_commit:ap.error('measurement commit required')
    if args.mode in RUNS:raise SystemExit(prior.capture(root,args.measurement_commit,args.mode))
    raise SystemExit(reference(root,args.measurement_commit))
