#!/usr/bin/env python3
"""C122 same-profile boundary canary against the preserved C93 ON capture."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from c66_wave_id_diagnostic import IDS
from c58_resource_canary import MODEL
from host_resource_policy import GIB, freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, file_identity, relevant_environment, sha256
import c70_full_boundary_gate as gate
import c122_decode_trace as campaign

RUN_ID='c122-numeric-canary-on01'
BIN=campaign.BUILD/'c122_session_boundary_capture'
REFERENCE=campaign.REPO/'results/c93-session-wave-8k-boundary-20260928T2049Z/raw/c93-p12-session-wave-on01.capture'
REFERENCE_MANIFEST=REFERENCE.parent/'c93-p12-session-wave-on01.json'
CAP=18*GIB


def save_new(path,row):
    with Path(path).open('x') as out:
        json.dump(row,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')


def expected(root):
    policy=strict_json((root/'resource-policy.json').read_text())
    c105=strict_json((campaign.REPO/'results/c105-c84-8k-trace-boundary-20260928T2335Z/protocol.json').read_text())
    if campaign.git('-C',campaign.BACKEND,'rev-parse','HEAD')!=campaign.BACKEND_SHA or \
       campaign.git('-C',campaign.BACKEND,'status','--porcelain') or not BIN.is_file():
        raise GateError('C122 canary backend/probe changed')
    p={'schema':'c122-same-profile-canary-v1','run_id':RUN_ID,
       'objective':'C122 instrumentation source preserves C75 ON same-profile active states and full logits in C93 189+32 boundary',
       'reference_manifest_sha256':sha256(REFERENCE_MANIFEST),
       'numeric_ids_sha256':sha256(IDS),
       'model_sha256':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
       'model_stat':file_identity(MODEL),'backend_sha':campaign.BACKEND_SHA,
       'backend_tree':campaign.git('-C',campaign.BACKEND,'rev-parse','HEAD^{tree}'),
       'binary_sha256':sha256(BIN),
       'backend_libraries_sha256':backend_library_hashes(str(BIN),campaign.BACKEND),
       'profile':c105['profile'],'call_plan':c105['call_plan'],
       'resources':freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP),
       'limits':{'timeout_s':600},
       'output_root':str((root/'raw').resolve()),'default_changed':False}
    validate_resource_protocol(p)
    return p


def freeze(root):
    save_new(root/'canary-protocol.json',expected(root))
    save_new(root/'canary-preflight.json',{'schema':'c122-canary-freeze-v1',
        'utc':datetime.now(timezone.utc).isoformat(),
        'protocol_sha256':sha256(root/'canary-protocol.json'),
        'status':'FROZEN_NOT_MEASURED'})


def run(root,commit):
    if campaign.git('rev-parse','HEAD')!=commit or campaign.git('status','--porcelain') or \
       relevant_environment(os.environ):
        raise GateError('C122 canary measurement worktree/environment changed')
    p=expected(root)
    if p!=strict_json((root/'canary-protocol.json').read_text()) or \
       sha256(root/'canary-protocol.json')!=strict_json((root/'canary-preflight.json').read_text())['protocol_sha256']:
        raise GateError('C122 canary freeze changed')
    no_other_model()
    stem=root/'raw'/RUN_ID
    capture=Path(str(stem)+'.capture')
    if capture.exists() or Path(str(stem)+'.json').exists():
        raise GateError('C122 canary output identity already used')
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
        '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
        '--run-id',RUN_ID,'--model-id','gpt-oss-120b-mxfp4-gguf',
        '--backend','streaming','--backend-root',str(campaign.BACKEND),
        '--output-root',str((root/'raw').resolve()),
        '--variant','P12-C122-trace-source-ON-no-trace-file',
        '--workload',str(IDS),'--cache-condition','fresh-expert-pools-page-cache-uncontrolled',
        '--timeout-s','600','--resource-protocol',str(root/'canary-protocol.json'),
        '--require-telemetry','--ready-marker','C80_CONTEXT_READY',
        '--env','TESY_CPU_WAVE_SKIP_PARKED=1','--',str(BIN),str(MODEL),
        str(IDS),str(capture),'--ngl','12']
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    receipt={'schema':'c122-canary-receipt-v1','run_id':RUN_ID,
        'measurement_commit':commit,'scope_returncode':proc.returncode,
        'scope_stderr_tail':proc.stderr[-1200:],
        'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    manifest=Path(str(stem)+'.json')
    if manifest.is_file():
        m=strict_json(manifest.read_text())
        receipt['raw_manifest_sha256']=sha256(manifest)
        receipt['stop_reason']=m.get('stop_reason')
        receipt['returncode']=m.get('returncode')
        if proc.returncode==0 and m.get('returncode')==0 and m.get('stop_reason') is None:
            try:
                if any(sha256(Path(str(stem)+suffix))!=digest for suffix,digest in
                       m['output_sha256'].items()) or \
                   m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256']:
                    raise GateError('C122 canary raw/library identity changed')
                reference_manifest=strict_json(REFERENCE_MANIFEST.read_text())
                reference_stem=REFERENCE.parent/'c93-p12-session-wave-on01'
                if sha256(REFERENCE_MANIFEST)!=p['reference_manifest_sha256'] or \
                   any(sha256(Path(str(reference_stem)+suffix))!=digest for suffix,digest in
                       reference_manifest['output_sha256'].items()):
                    raise GateError('C122 reference capture identity changed')
                left=gate.inspect(capture,skip_on=True)
                right=gate.inspect(REFERENCE,skip_on=True)
                if any(left[k]!=right[k] for k in ('core','logits','masks')):
                    raise GateError('C122 same-profile full-logit/state mismatch')
                receipt['status']='PASS_SAME_PROFILE_BOUNDARY'
                receipt['coverage']=left['coverage']
                receipt['capture_output_count']=len(m['output_sha256'])
            except Exception as exc:
                receipt['status']='FAIL_SAME_PROFILE_OR_EVIDENCE'
                receipt['reason']=f'{type(exc).__name__}: {exc}'
    else:
        receipt['reason']='bounded raw manifest absent'
    save_new(root/'raw'/f'{RUN_ID}-receipt.json',receipt)
    print(json.dumps({'status':receipt['status'],'reason':receipt.get('reason')}))
    return 0 if receipt['status']=='PASS_SAME_PROFILE_BOUNDARY' else 1


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('freeze','run'))
    ap.add_argument('root',type=Path);ap.add_argument('--measurement-commit')
    a=ap.parse_args();root=a.root.resolve()
    if a.mode=='freeze':freeze(root)
    else:
        if not a.measurement_commit:ap.error('run needs full SHA')
        raise SystemExit(run(root,a.measurement_commit))
