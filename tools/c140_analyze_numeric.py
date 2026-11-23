#!/usr/bin/env python3
"""Revalidate C140 numeric admission and all raw manifests without new inference."""
import json
from pathlib import Path
from c2_gate import GateError,strict_json
from c94_session_wave_8k_reference import tree_digest,validate_result
from run_bounded import sha256
import c139_slots44_numeric as gate

ROOT=gate.REPO/'results/c140-slots44-numeric-20260929T2324Z'

def analyze():
    gate.configure(ROOT);p=gate.expected(ROOT)
    if p!=strict_json((ROOT/'protocol.json').read_text()):raise GateError('C140 frozen protocol changed')
    unit=strict_json((ROOT/'unit-receipt.json').read_text());ref=strict_json((ROOT/'reference-summary.json').read_text())
    boundary=strict_json((ROOT/'boundary-summary.json').read_text())
    if unit['status']!='PASS_UNIFORM44_NUMERIC_BOUNDARY_AND_36_FFN' or unit['elapsed_s']+60>1800 or \
       boundary['status']!='SAME_PROFILE_BITWISE_PASS' or ref['status']!='PASS_FULL_REFERENCE' or \
       ref['layers']!=list(range(36)) or (ref['numeric_rows'],ref['masked_rows'])!=(250,2):
        raise GateError('C140 numeric summaries/envelope failed')
    captures={arm:gate.verify_capture(ROOT,p,arm) for arm in ('off','on')}
    if tree_digest(ROOT/'raw/c140-slots44-on01.capture')!=ref['capture_tree']:raise GateError('C140 ON capture changed')
    refs=[]
    for layer in range(36):
        rid=f'c140-ref-l{layer:02d}-01';rp=ROOT/f'{rid}-receipt.json';mp=ROOT/'raw'/f'{rid}.json'
        receipt=strict_json(rp.read_text());m=strict_json(mp.read_text())
        if receipt['status']!='PASS_CANONICAL_LAYER' or receipt['raw_manifest_sha256']!=sha256(mp) or \
           m['run_id']!=rid or m['variant']!=f'P12-C140-slots44-canonical-layer{layer}' or \
           m['limits']['resource_protocol_sha256']!=sha256(ROOT/'protocol.json') or \
           m['mapped_backend_libraries_sha256']!=p['backend_libraries_sha256'] or \
           m['resource_authority']!=p['resources'] or m['returncode']!=0 or m['stop_reason'] is not None:
            raise GateError('C140 reference identity failed')
        for suffix,h in m['output_sha256'].items():
            if sha256(ROOT/'raw'/f'{rid}{suffix}')!=h:raise GateError('C140 reference raw hash changed')
        if not validate_result(strict_json((ROOT/'raw'/f'{rid}.stdout').read_text()),layer):
            raise GateError('C140 reference numerical gate failed')
        refs.append({'layer':layer,'manifest_sha256':sha256(mp),'receipt_sha256':sha256(rp),'elapsed_s':m['elapsed_s']})
    decision={'schema':'c140-decision-v1','status':unit['status'],'measurement_commit':unit['measurement_commit'],
        'evidence':'MEDIDO_NO_TARGET','profile':'C75 ON/OFF P12 uniform44 ub32 ctx8192 preloadON fullSWA KVF16 E20',
        'captures':captures,'boundary_sha256':sha256(ROOT/'boundary-summary.json'),
        'reference_sha256':sha256(ROOT/'reference-summary.json'),'reference_layers':36,'numeric_rows':250,
        'unit_elapsed_s':unit['elapsed_s'],'physical_with_inventory_s':unit['elapsed_s']+60,
        'gpu_peak_mib':max(c['maxima']['gpu_used_mib'] for c in captures.values()),
        'limits':['189+32 short boundary; not independent full8K attention/KV','quality/holdout/session/retrieval44 NOT_RUN','no timing promotion'],
        'next_gate':'new two-pair uniform40/44 same C75 server/E20 nominal153 screen; no eviction patch',
        'M3':'NOT_INHERITED_FROM_SLOTS40','M4':'NOT_DEMONSTRATED','publication':'LOCAL_ONLY','default_changed':False}
    manifest={'schema':'c140-raw-manifest-v1','measurement_commit':unit['measurement_commit'],
        'raw':{str(f.relative_to(ROOT/'raw')):{'bytes':f.stat().st_size,'sha256':sha256(f)}
               for f in sorted((ROOT/'raw').rglob('*')) if f.is_file()},'references':refs}
    return decision,manifest

if __name__=='__main__':
    for name,row in zip(('decision.json','manifest.json'),analyze()):
        gate.prior.save_new(ROOT/name,row)
    print(json.dumps({'status':strict_json((ROOT/'decision.json').read_text())['status']}))
