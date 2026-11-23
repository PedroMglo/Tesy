#!/usr/bin/env python3
"""Preserve the resource-stop C78 raw without treating it as a numeric result."""
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256

ROOT = Path(__file__).resolve().parents[1] / 'results/c78-session-wave-repeat-20260928T1929Z'
RUN = 'c78-p12-session-wave-on-repeat01'
COMMIT = 'cd4d230f0dcc4efd00a7c3056beeff21be9dc57f'


def save(path, value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')


def main():
    receipt = strict_json((ROOT/'raw'/(RUN+'-receipt.json')).read_text())
    manifest_path = ROOT/'raw'/(RUN+'.json')
    raw = strict_json(manifest_path.read_text())
    if receipt['measurement_commit'] != COMMIT or \
       receipt['status'] != 'FAIL_RESOURCES_OR_EVIDENCE' or \
       receipt['stop_reason'] != 'CGROUP_PREVENTIVE_MARGIN' or \
       receipt['raw_manifest_sha256'] != sha256(manifest_path) or \
       raw['stop_reason'] != 'CGROUP_PREVENTIVE_MARGIN' or \
       raw['cgroup_end']['swap_current'] != 0 or \
       any(raw['cgroup_end']['events'][k] for k in ('max','oom','oom_kill')):
        raise GateError('C78 stop attribution/raw identity changed')
    for suffix,digest in raw['output_sha256'].items():
        if sha256(ROOT/'raw'/(RUN+suffix)) != digest:
            raise GateError('C78 bounded raw hash changed')
    files = {}
    for path in sorted((ROOT/'raw').rglob('*')):
        if path.is_file():
            files[str(path.relative_to(ROOT))] = {'bytes':path.stat().st_size,
                                                  'sha256':sha256(path)}
    capture = ROOT/'raw'/(RUN+'.capture')
    evidence = {'schema':'c78-evidence-v1','measurement_commit':COMMIT,
                'stop_reason':raw['stop_reason'],'elapsed_s':raw['elapsed_s'],
                'ready_elapsed_s':raw.get('ready_elapsed_s'),
                'maxima':raw['maxima'],
                'capture_index_complete':(capture/'index.tsv').is_file(),
                'capture_file_count':sum(p.is_file() for p in capture.rglob('*')),
                'capture_bytes':sum(p.stat().st_size for p in capture.rglob('*') if p.is_file()),
                'numeric_comparison':'NOT_RUN_INCOMPLETE_CAPTURE',
                'cgroup_end_events':raw['cgroup_end']['events'],
                'cgroup_end_swap':raw['cgroup_end']['swap_current']}
    save(ROOT/'resource-summary.json', evidence)
    save(ROOT/'manifest.json',{'schema':'c78-raw-manifest-v1',
        'measurement_commit':COMMIT,'protocol_sha256':sha256(ROOT/'protocol.json'),
        'raw_file_count':len(files),'raw_total_bytes':sum(v['bytes'] for v in files.values()),
        'raw_sha256':files,'publication':'local only; raw untracked'})
    save(ROOT/'decision.json',{'schema':'c78-decision-v1',
        'status':'FAIL_RESOURCES_OR_EVIDENCE','failure_attribution':'CGROUP_PREVENTIVE_MARGIN',
        'measurement_commit':COMMIT,'evidence':evidence,
        'numeric_fidelity':'NOT_RUN_INCOMPLETE_CAPTURE',
        'old_valid_results':['C76b full boundary PASS','C77 canonical FFN PASS'],
        'next_action':'New identity only after a fresh host admission supports a cap with margin above the observed C78 cgroup file charge; do not retry E16.',
        'default_changed':False})
    (ROOT/'LEDGER.md').write_text(
        '# C78 fresh ON repeat\n\n'
        f'- Measurement commit `{COMMIT}`; one C75/P12 ON attempt, no retry.\n'
        f'- FAIL_RESOURCES_OR_EVIDENCE: `{raw["stop_reason"]}` at {raw["elapsed_s"]} s, cgroup peak {raw["maxima"]["cgroup_peak_bytes"]} B under E16; file charge {raw["maxima"]["cgroup_file_bytes"]} B.\n'
        '- Swap, cgroup max and OOM events zero. Capture incomplete without index; no numeric comparison or timing claim.\n'
        '- C76b/C77 PASSs remain scoped and unchanged. Next: new cap admission, not an E16 retry.\n')
    print(json.dumps({'status':'FAIL_RESOURCES_OR_EVIDENCE',
                      'stop_reason':raw['stop_reason'],'raw_files':len(files),
                      'capture_index_complete':evidence['capture_index_complete']}))


if __name__ == '__main__':
    main()
