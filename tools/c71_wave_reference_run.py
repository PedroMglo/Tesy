#!/usr/bin/env python3
"""Bounded C57 P12 canonical resident FFN references, CPU/GPU boundary first."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

from c2_gate import GateError,strict_json
from c17_thermal_recovery import no_other_model
from c58_resource_canary import MODEL
from host_resource_policy import GIB,derive_policy,freeze_protocol_resource_limits,validate_resource_protocol
from run_bounded import backend_library_hashes,file_identity,sha256
from c66_wave_id_diagnostic import BACKEND
from c70_full_boundary_gate import inspect

REPO=Path(__file__).resolve().parents[1]
SOURCE_ROOT=REPO/'results/c70-full-wave-boundary-20260928T1652Z'
CAPTURE=SOURCE_ROOT/'raw/c70-p12-wave-on01.capture'
BOUNDARY=SOURCE_ROOT/'boundary-summary.json'
CAPTURE_MANIFEST=SOURCE_ROOT/'manifest.json'
BINARY=REPO/'tools/c71_layer_reference'
CAP=18*GIB
WITNESS=(25,26,27,28,24,29)
PHASES=('prefill0','prefill128','prefill_final','decode0','decode1','decode7','decode31')


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],text=True).strip()


def write_new(path,obj):
    with path.open('x') as out:json.dump(obj,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')


def tree_digest(path):
    files=sorted(p for p in path.iterdir() if p.is_file())
    digest=hashlib.sha256()
    for item in files:
        name=item.name.encode();size=item.stat().st_size
        digest.update(len(name).to_bytes(4,'big'));digest.update(name)
        digest.update(size.to_bytes(8,'big'))
        digest.update(bytes.fromhex(sha256(item)))
    return {'files':len(files),'total_bytes':sum(p.stat().st_size for p in files),
            'sha256_name_size_content_v1':digest.hexdigest()}


def frozen(root):
    stat=file_identity(MODEL)
    source_protocol=strict_json((SOURCE_ROOT/'protocol.json').read_text())
    if stat!=source_protocol['model_stat']:
        raise GateError('C70 model identity changed')
    boundary=strict_json(BOUNDARY.read_text())
    if boundary['status']!='SAME_PROFILE_BITWISE_PASS' or \
       boundary['numeric_states']!=250 or boundary['masked_states']!=2:
        raise GateError('C70 observer boundary incomplete')
    source_manifest=strict_json(CAPTURE_MANIFEST.read_text())
    for path,record in source_manifest['raw_sha256'].items():
        if path.startswith('raw/c70-p12-wave-on01.capture/'):
            file=SOURCE_ROOT/path
            if file.stat().st_size!=record['bytes'] or sha256(file)!=record['sha256']:
                raise GateError('C70 ON raw capture changed')
    prior=tree_digest(CAPTURE)
    coverage=inspect(CAPTURE,skip_on=True)['coverage']
    if coverage['numeric_states']!=250 or coverage['masked_states']!=2:
        raise GateError('C70 ON capture coverage changed')
    snapshot=strict_json((root/'snapshot.json').read_text())
    policy=strict_json((root/'resource-policy.json').read_text())
    if derive_policy(snapshot=snapshot)!=policy or \
       any(stat[key]!=snapshot['model_stat'][other] for key,other in
           (('dev','dev'),('inode','inode'),('size_bytes','size_bytes'),('mtime_ns','mtime_ns'))):
        raise GateError('fresh C64 inventory/model changed')
    resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=CAP)
    libs=backend_library_hashes(str(BINARY),BACKEND)
    if not libs or git('-C',BACKEND,'rev-parse','HEAD')!= \
       '1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22' or \
       git('-C',BACKEND,'status','--porcelain'):
        raise GateError('canonical backend/library identity changed')
    protocol={'schema':'c71-p12-wave-reference-protocol-v1','campaign_id':root.name,
              'objective':'C57 P12 wave ON streamed routed FFN versus resident canonical same-device layer',
              'alternative':'wave skip keeps OFF/ON equality but differs from independently resident routed FFN',
              'model_stat':stat,'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d',
              'backend_sha':git('-C',BACKEND,'rev-parse','HEAD'),
              'backend_tree':git('-C',BACKEND,'rev-parse','HEAD^{tree}'),
              'backend_libraries_sha256':libs,
              'binary_sha256':sha256(BINARY),
              'source_sha256':sha256(REPO/'tools/c7_layer_reference.cpp'),
              'runner_sha256':sha256(__file__),
              'monitor_sha256':sha256(REPO/'tools/run_bounded.py'),
              'capture_tree':prior,'capture_index_sha256':sha256(CAPTURE/'index.tsv'),
              'boundary_summary_sha256':sha256(BOUNDARY),
              'C70_manifest_sha256':sha256(CAPTURE_MANIFEST),
              'witness_layers':list(WITNESS),
              'remaining_layers':[i for i in range(36) if i not in WITNESS],
              'expected':{'numeric_rows':250,'masked_rows':2,'canonical_layer_bytes':1697956352,
                          'first_gpu_layer':25,'phases':list(PHASES),
                          'routing_ids':'ordered equality','routing_weights':'bitwise',
                          'ffn_output':'bitwise','reference_compute_device':'same as streamed'},
              'resources':resources,'limits':{'timeout_s_per_layer':180},
              'stop_rule':'first layer mismatch, nonfinite, identity or resource failure ends phase; no retry',
              'publication':'local only; raw untracked'}
    validate_resource_protocol(protocol)
    return protocol


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir():
        raise GateError('new C71 root/raw required')
    protocol=frozen(root)
    write_new(root/'protocol.json',protocol)
    write_new(root/'preflight.json',{'schema':'c71-freeze-v1',
        'utc':datetime.now(timezone.utc).isoformat(),'status':'FROZEN_NOT_MEASURED',
        'snapshot_sha256':sha256(root/'snapshot.json'),
        'resource_policy_sha256':sha256(root/'resource-policy.json'),
        'protocol_sha256':sha256(root/'protocol.json'),
        'selected_cap_bytes':CAP})
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','root':str(root)}))


def validate_result(result,layer):
    device='cpu' if layer<25 else 'gpu'
    if result['schema']!='c7-p12-layer-reference-v1' or \
       result['layer']!=layer or result['device']!=device or \
       result['canonical_layer_bytes']!=1697956352 or \
       [row['phase'] for row in result['rows']]!=list(PHASES) or \
       result['numeric_rows']!=(5 if layer==35 else 7) or \
       result['masked_rows']!=(2 if layer==35 else 0):
        raise GateError('canonical layer schema/placement/row count invalid')
    for row in result['rows']:
        if row['state']=='N/A_MASKED':
            if layer!=35 or row['phase'] not in ('prefill0','prefill128'):
                raise GateError('unexpected masked canonical row')
            continue
        if row['state']!='NUMERIC' or not row['routing_ids_equal'] or \
           not row['routing_weights_bitwise'] or not row['ffn_bitwise'] or \
           row['routing_weights_nonfinite'] or row['ffn_nonfinite']:
            return False
    return bool(result['all_bitwise'])


def one(root,layer,commit,protocol):
    run_id=f'c71-p12-ref-l{layer:02d}-01'
    device='cpu' if layer<25 else 'gpu'
    no_other_model()
    command=['systemd-run','--user','--scope','-p',f'MemoryMax={CAP}',
             '-p','MemorySwapMax=0','--','python3','tools/run_bounded.py',
             '--run-id',run_id,'--model-id','gpt-oss-120b-mxfp4-gguf',
             '--backend','streaming','--backend-root',str(BACKEND),
             '--output-root',str((root/'raw').resolve()),
             '--variant',f'P12-C57-canonical-layer{layer}-{device}',
             '--workload',str(CAPTURE/'index.tsv'),
             '--cache-condition','resident-canonical-one-layer-page-cache-uncontrolled',
             '--timeout-s','180','--resource-protocol',str(root/'protocol.json'),
             '--require-telemetry','--',str(BINARY),str(MODEL),str(CAPTURE),
             str(layer),'--ngl','12']
    process=subprocess.run(command,capture_output=True,text=True,check=False)
    receipt={'schema':'c71-layer-receipt-v1','run_id':run_id,'layer':layer,'device':device,
             'measurement_commit':commit,'scope_returncode':process.returncode,
             'scope_stderr_tail':process.stderr[-1000:],'status':'FAIL_RESOURCES_OR_EVIDENCE'}
    stem=root/'raw'/run_id
    manifest_path=Path(str(stem)+'.json')
    if not manifest_path.is_file():
        receipt['reason']='bounded manifest absent'
        return receipt
    manifest=strict_json(manifest_path.read_text())
    receipt.update(raw_manifest_sha256=sha256(manifest_path),
                   elapsed_s=manifest.get('elapsed_s'),returncode=manifest.get('returncode'),
                   stop_reason=manifest.get('stop_reason'),maxima=manifest.get('maxima'))
    if process.returncode!=0 or manifest['returncode']!=0 or manifest['stop_reason'] is not None:
        receipt['reason']='reference process/monitor failure'
        return receipt
    try:
        if manifest['backend_sha']!=protocol['backend_sha'] or \
           manifest['binary_sha256']!=protocol['binary_sha256'] or \
           manifest['backend_libraries_sha256']!=protocol['backend_libraries_sha256'] or \
           manifest['mapped_backend_libraries_sha256']!=protocol['backend_libraries_sha256'] or \
           not manifest['mapped_libraries_match_ldd'] or \
           manifest['artifact_identity']['stat_at_launch']!=protocol['model_stat'] or \
           manifest['artifact_identity']['stat_at_end']!=protocol['model_stat'] or \
           manifest['workload_sha256']!=protocol['capture_index_sha256'] or \
           manifest['resource_authority']!=protocol['resources'] or \
           manifest['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json'):
            raise GateError('reference backend/model/capture/resource identity changed')
        for suffix,digest in manifest['output_sha256'].items():
            if sha256(Path(str(stem)+suffix))!=digest:
                raise GateError('reference raw hash changed')
        result=strict_json(Path(str(stem)+'.stdout').read_text())
        receipt['reference_sha256']=sha256(Path(str(stem)+'.stdout'))
        receipt['rows']=result['rows']
        if not validate_result(result,layer):
            receipt.update(status='FAIL_SAME_PROFILE_FIDELITY',reason='canonical row differs')
        else:
            receipt.update(status='PASS_CANONICAL_LAYER',numeric_rows=result['numeric_rows'],
                           masked_rows=result['masked_rows'])
    except (GateError,KeyError,TypeError,ValueError,OSError) as exc:
        receipt['reason']=f'{type(exc).__name__}: {exc}'
    return receipt


def run(root,phase,commit):
    if git('rev-parse','HEAD')!=commit or git('status','--porcelain'):
        raise GateError('C71 measurement commit/tree not clean')
    protocol=strict_json((root/'protocol.json').read_text())
    pre=strict_json((root/'preflight.json').read_text())
    if frozen(root)!=protocol or pre['protocol_sha256']!=sha256(root/'protocol.json'):
        raise GateError('C71 frozen source/capture/resource identity changed')
    if phase=='remaining':
        witness=strict_json((root/'witness-summary.json').read_text())
        if witness['status']!='PASS_WITNESS' or witness['layers']!=list(WITNESS):
            raise GateError('C71 witness prerequisite absent')
    layers=WITNESS if phase=='witness' else tuple(protocol['remaining_layers'])
    receipts=[]
    for layer in layers:
        if file_identity(MODEL)!=protocol['model_stat'] or \
           sha256(BINARY)!=protocol['binary_sha256']:
            raise GateError('C71 per-layer model/binary identity changed')
        receipt=one(root,layer,commit,protocol)
        receipts.append(receipt)
        print(json.dumps({'layer':layer,'status':receipt['status'],
                          'reason':receipt.get('reason'),'elapsed_s':receipt.get('elapsed_s')}),flush=True)
        if receipt['status']!='PASS_CANONICAL_LAYER':break
    for receipt in receipts:
        write_new(root/(receipt['run_id']+'-receipt.json'),receipt)
    status=('PASS_WITNESS' if phase=='witness' else 'PASS_FULL_REFERENCE') if \
           len(receipts)==len(layers) and all(r['status']=='PASS_CANONICAL_LAYER' for r in receipts) else \
           next((r['status'] for r in receipts if r['status']!='PASS_CANONICAL_LAYER'),
                'FAIL_RESOURCES_OR_EVIDENCE')
    summary={'schema':'c71-reference-summary-v1','phase':phase,'status':status,
             'measurement_commit':commit,'layers':[r['layer'] for r in receipts],
             'numeric_rows':sum(r.get('numeric_rows',0) for r in receipts),
             'masked_rows':sum(r.get('masked_rows',0) for r in receipts),
             'run_ids':[r['run_id'] for r in receipts]}
    write_new(root/('witness-summary.json' if phase=='witness' else 'full-summary.json'),summary)
    return 0 if status.startswith('PASS_') else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('freeze','witness','remaining'))
    parser.add_argument('root',type=Path)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args();root=args.root.resolve()
    if args.mode=='freeze':freeze(root)
    else:
        if not args.measurement_commit:parser.error('reference phase needs measurement commit')
        raise SystemExit(run(root,args.mode,args.measurement_commit))
