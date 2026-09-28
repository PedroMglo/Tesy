#!/usr/bin/env python3
"""Close C77 resident FFN references from immutable per-layer receipts."""
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c77_session_wave_reference as unit

ROOT = unit.REPO / 'results/c77-session-wave-reference-20260928T1922Z'
COMMITS = {'witness':'12195f97a802332b59d7a0f88d8008cfe937f608',
           'remaining':'e7ccb0ede374c15c6caf0e14d9246f5794aff8e4'}


def save(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def main():
    p = strict_json((ROOT / 'protocol.json').read_text())
    summaries = {phase:strict_json((ROOT / name).read_text())
                 for phase,name in (('witness','witness-summary.json'),
                                    ('remaining','full-summary.json'))}
    if summaries['witness']['status'] != 'PASS_WITNESS' or \
       summaries['remaining']['status'] != 'PASS_FULL_REFERENCE' or \
       any(summaries[phase]['measurement_commit'] != commit
           for phase,commit in COMMITS.items()):
        raise GateError('C77 summary/measurement identity failed')
    layers = summaries['witness']['layers'] + summaries['remaining']['layers']
    if sorted(layers) != list(range(36)) or \
       sum(s['numeric_rows'] for s in summaries.values()) != 250 or \
       sum(s['masked_rows'] for s in summaries.values()) != 2:
        raise GateError('C77 36-layer/252-position coverage failed')
    receipts = []
    maxima = {k:0 for k in ('rss_bytes','cgroup_peak_bytes','gpu_used_mib',
                            'gpu_temperature_c','cpu_tctl_c','nvme_composite_c','swap_bytes')}
    for phase in ('witness','remaining'):
        for layer in summaries[phase]['layers']:
            run = f'c77-p12-ref-l{layer:02d}-01'
            receipt = strict_json((ROOT / (run + '-receipt.json')).read_text())
            raw = strict_json((ROOT / 'raw' / (run + '.json')).read_text())
            if receipt['status'] != 'PASS_CANONICAL_LAYER' or \
               receipt['measurement_commit'] != COMMITS[phase] or \
               receipt['raw_manifest_sha256'] != sha256(ROOT / 'raw' / (run + '.json')) or \
               raw['returncode'] != 0 or raw['stop_reason'] is not None or \
               raw['backend_sha'] != p['backend_sha'] or \
               raw['mapped_backend_libraries_sha256'] != p['backend_libraries_sha256'] or \
               not raw['mapped_libraries_match_ldd'] or \
               raw['cgroup_end']['swap_current'] != 0:
                raise GateError(f'C77 receipt/raw failure layer {layer}')
            for event in ('max','oom','oom_kill'):
                if raw['cgroup_end']['events'][event] or raw['cgroup_end']['events_local'][event]:
                    raise GateError(f'C77 cgroup event {event} layer {layer}')
            for suffix,digest in raw['output_sha256'].items():
                if sha256(ROOT / 'raw' / (run + suffix)) != digest:
                    raise GateError(f'C77 raw output hash mismatch layer {layer}')
            for key in maxima:
                maxima[key] = max(maxima[key], receipt['maxima'][key])
            receipts.append(receipt)
    raw_hashes = {}
    for path in sorted((ROOT/'raw').rglob('*')):
        if path.is_file():
            raw_hashes[str(path.relative_to(ROOT))] = {'bytes':path.stat().st_size,
                                                       'sha256':sha256(path)}
    resource = {'schema':'c77-resource-summary-v1','maxima':maxima,
                'layer_loads':36,'sum_bounded_elapsed_s':sum(r['elapsed_s'] for r in receipts),
                'cgroup_cap_bytes':p['resources']['cgroup']['memory_max_bytes'],
                'swap_events_oom':'ZERO_ALL_36'}
    save(ROOT/'resource-summary.json',resource)
    with (ROOT/'runs.jsonl').open('x') as out:
        for receipt in receipts:
            out.write(json.dumps(receipt,sort_keys=True,allow_nan=False)+'\n')
    manifest = {'schema':'c77-raw-manifest-v1','measurement_commits':COMMITS,
                'backend_commit':p['backend_sha'],'protocol_sha256':sha256(ROOT/'protocol.json'),
                'capture_manifest_sha256':p['C76b_manifest_sha256'],
                'raw_file_count':len(raw_hashes),
                'raw_total_bytes':sum(x['bytes'] for x in raw_hashes.values()),
                'raw_sha256':raw_hashes,'publication':'local only; raw untracked'}
    save(ROOT/'manifest.json',manifest)
    decision = {'schema':'c77-decision-v1','status':'PASS_FULL_RESIDENT_CANONICAL_FFN_TESTED_SCOPE',
                'measurement_commits':COMMITS,'backend_commit':p['backend_sha'],
                'numeric_rows':250,'masked_rows':2,'canonical_layer_loads':36,
                'resources':resource,'claim_limit':'P12 n_ctx4096 preload OFF routed FFN only; independent attention/KV and 8192 session profile NOT_RUN',
                'preserved_failures':['C48 FAIL_SAME_PROFILE_FIDELITY',
                                      'C61 FAIL_NUMERIC_RUNTIME_ASSERTION',
                                      'C66 FAIL_NUMERIC_RUNTIME_ASSERTION'],
                'next_action':'Fresh ON repeat on C75 build, then prospective n_ctx8192 preload-ON session gate',
                'default_changed':False}
    save(ROOT/'decision.json',decision)
    (ROOT/'LEDGER.md').write_text(
        '# C77 same-build resident canonical FFN\n\n'
        f'- Witness measurement `{COMMITS["witness"]}`: layers 25–28 and 24/29 PASS.\n'
        f'- Remaining measurement `{COMMITS["remaining"]}`: 30 layers PASS.\n'
        '- 36 resident loads; 250 numeric rows bitwise for ordered router IDs, weights and FFN; two explicit masked rows.\n'
        f'- Resource maxima and {len(raw_hashes)} raw hashes in compact JSON; swap/OOM/max events zero.\n'
        '- Attention/KV reference, 8192 session, quality and M4: NOT_RUN. C48/C61/C66 FAILs unchanged.\n'
        '- Next: fresh repeat and server-profile bridge. No remote publication/default change.\n')
    print(json.dumps({'status':decision['status'],'maxima':maxima,
                      'raw_files':len(raw_hashes),'elapsed_s':resource['sum_bounded_elapsed_s']}))


if __name__ == '__main__':
    main()
