#!/usr/bin/env python3
"""Close the frozen C76b full boundary without rerunning inference."""
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c70_full_boundary_gate as gate
import c76_session_wave_boundary as unit

ROOT = unit.REPO / 'results/c76b-session-wave-boundary-20260928T1918Z'
COMMIT = '9985ebf89e9dcb20f12493505c1a4ae4999d39f9'


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    p = strict_json((ROOT / 'protocol.json').read_text())
    arms = {}
    receipts = []
    for arm, run in unit.RUNS.items():
        receipt = strict_json((ROOT / 'raw' / (run + '-receipt.json')).read_text())
        if receipt['measurement_commit'] != COMMIT or receipt['status'] != 'PASS_FULL_CAPTURE_SINGLE_ARM':
            raise GateError('C76b arm receipt incomplete')
        arms[arm] = unit.verify(ROOT, p, arm)
        receipts.append(receipt)
    off = ROOT / 'raw' / (unit.RUNS['off'] + '.capture')
    on = ROOT / 'raw' / (unit.RUNS['on'] + '.capture')
    comparison = gate.compare(off, on)
    old = gate.inspect(unit.OLD / 'raw/c70-p12-wave-off01.capture', skip_on=False)
    current = gate.inspect(off, skip_on=False)
    cross = {'core_equal':sum(old['core'][k] == current['core'][k] for k in old['core']),
             'core_total':len(old['core']),
             'full_logits_equal':{phase:old['logits'][phase] == current['logits'][phase]
                                  for phase in old['logits']},
             'scope':'cross-build descriptive only; not the same-profile gate'}
    summary = {'schema':'c76b-boundary-summary-v1','measurement_commit':COMMIT,
               'backend_commit':unit.BACKEND_SHA,'arms':arms,
               'comparison':comparison,'cross_build_C70_OFF':cross}
    save(ROOT / 'boundary-summary.json', summary)
    with (ROOT / 'runs.jsonl').open('x') as stream:
        for receipt in receipts:
            stream.write(json.dumps(receipt, sort_keys=True, allow_nan=False) + '\n')
    raw = {}
    for path in sorted((ROOT / 'raw').rglob('*')):
        if path.is_file():
            raw[str(path.relative_to(ROOT))] = {'bytes':path.stat().st_size,'sha256':sha256(path)}
    manifest = {'schema':'c76b-raw-manifest-v1','measurement_commit':COMMIT,
                'backend_commit':unit.BACKEND_SHA,
                'protocol_sha256':sha256(ROOT / 'protocol.json'),
                'boundary_summary_sha256':sha256(ROOT / 'boundary-summary.json'),
                'raw_file_count':len(raw),'raw_total_bytes':sum(x['bytes'] for x in raw.values()),
                'raw_sha256':raw,'publication':'local only; raw untracked'}
    save(ROOT / 'manifest.json',manifest)
    valid = comparison['status'] == 'SAME_PROFILE_BITWISE_PASS'
    decision = {'schema':'c76b-decision-v1',
        'status':'SAME_PROFILE_BITWISE_PASS_FULL_BOUNDARY' if valid else 'FAIL_SAME_PROFILE_FIDELITY',
        'measurement_commit':COMMIT,'backend_commit':unit.BACKEND_SHA,
        'numeric_states':comparison['numeric_states'],'masked_states':comparison['masked_states'],
        'core_stage_comparisons':comparison['core_stage_comparisons'],
        'full_logit_vectors':comparison['full_logits'],
        'off_maxima':receipts[0]['maxima'],'on_maxima':receipts[1]['maxima'],
        'cross_build_C70_OFF':cross,'raw_file_count':len(raw),
        'preserved_failures':['C48 FAIL_SAME_PROFILE_FIDELITY',
                              'C61 FAIL_NUMERIC_RUNTIME_ASSERTION',
                              'C66 FAIL_NUMERIC_RUNTIME_ASSERTION'],
        'claim_limit':'P12 n_ctx4096 preload OFF full boundary only; independent attention/KV, 8192 session and quality NOT_RUN',
        'next_action':'C75 same-build resident canonical FFN reference, then 8192 session numeric bridge before timing' if valid
                      else 'diagnose this new failure under a new identity before further C75 inference',
        'default_changed':False}
    save(ROOT / 'decision.json', decision)
    (ROOT / 'LEDGER.md').write_text(
        '# C76b session port full boundary\n\n'
        f'- Measurement commit `{COMMIT}`; C75 backend `{unit.BACKEND_SHA}`.\n'
        '- A mistyped SHA invocation was rejected before model load or run ID creation.\n'
        f'- OFF and ON receipts: PASS; 250 numeric states, 2 masked, {comparison["core_stage_comparisons"]} core stages and five full logits compared bitwise.\n'
        f'- Result: {decision["status"]}; CPU maxima OFF/ON {receipts[0]["maxima"]["cpu_tctl_c"]}/{receipts[1]["maxima"]["cpu_tctl_c"]} C (see receipts for full resources).\n'
        '- Cross-build C70 observations are descriptive. Resident reference, session profile and quality remain NOT_RUN.\n'
        '- Next: same-build canonical FFN reference before server performance.\n')
    print(json.dumps({'status':decision['status'],'raw_files':len(raw),
                      'cross_build':cross},sort_keys=True))
    return 0 if valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
