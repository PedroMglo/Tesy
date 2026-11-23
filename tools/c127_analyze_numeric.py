#!/usr/bin/env python3
"""Validate and summarize the frozen C127 numeric admission without changing raw."""

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c94_session_wave_8k_reference import tree_digest
from run_bounded import sha256


REPO = Path(__file__).resolve().parents[1]
RUNS = ('c127-slots40-off01', 'c127-slots40-on01')


def save_new(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def analyze(root):
    boundary = strict_json((root/'boundary-summary.json').read_text())
    reference = strict_json((root/'reference-summary.json').read_text())
    stage = strict_json((root/'capture-stage.json').read_text())
    if boundary['status'] != 'SAME_PROFILE_BITWISE_PASS' or \
       reference['status'] != 'PASS_FULL_REFERENCE' or \
       stage['boundary_summary_sha256'] != sha256(root/'boundary-summary.json') or \
       reference['capture_tree'] != stage['on_capture_tree'] or \
       reference['layers'] != list(range(36)) or \
       reference['numeric_rows'] != 250 or reference['masked_rows'] != 2:
        raise GateError('C127 numeric summaries disagree')
    raw = root/'raw'
    captures = {}
    for arm, run_id in zip(('off', 'on'), RUNS):
        mpath = raw/(run_id+'.json')
        receipt_path = raw/(run_id+'-receipt.json')
        m, receipt = strict_json(mpath.read_text()), strict_json(receipt_path.read_text())
        if receipt['status'] not in ('PASS_CAPTURE_ARM', 'PASS_SAME_PROFILE_BOUNDARY') or \
           receipt['manifest_sha256'] != sha256(mpath) or m['returncode'] != 0 or \
           m['stop_reason'] is not None or m['maxima']['swap_bytes'] != 0:
            raise GateError(f'C127 {arm} capture failed')
        for suffix, digest in m['output_sha256'].items():
            if sha256(raw/(run_id+suffix)) != digest:
                raise GateError(f'C127 {arm} raw changed')
        captures[arm] = {'manifest_sha256':sha256(mpath),
                         'receipt_sha256':sha256(receipt_path),
                         'tree':tree_digest(raw/(run_id+'.capture')),
                         'elapsed_s':m['elapsed_s'], 'maxima':m['maxima']}
    if captures['on']['tree'] != reference['capture_tree'] or \
       captures['off']['manifest_sha256'] != stage['off_manifest_sha256'] or \
       captures['on']['manifest_sha256'] != stage['on_manifest_sha256']:
        raise GateError('C127 capture tree/manifest changed')
    refs = []
    for layer in range(36):
        run_id = f'c127-ref-l{layer:02d}-01'
        mpath = raw/(run_id+'.json')
        rpath = root/(run_id+'-receipt.json')
        m, receipt = strict_json(mpath.read_text()), strict_json(rpath.read_text())
        if receipt['status'] != 'PASS_CANONICAL_LAYER' or receipt['layer'] != layer or \
           receipt['raw_manifest_sha256'] != sha256(mpath) or \
           m['returncode'] != 0 or m['stop_reason'] is not None or \
           m['maxima']['swap_bytes'] != 0:
            raise GateError(f'C127 reference layer {layer} failed')
        for suffix, digest in m['output_sha256'].items():
            if sha256(raw/(run_id+suffix)) != digest:
                raise GateError(f'C127 reference layer {layer} raw changed')
        refs.append({'layer':layer, 'receipt_sha256':sha256(rpath),
                     'manifest_sha256':sha256(mpath), 'elapsed_s':m['elapsed_s']})
    prior_path = REPO/'results/c126-wave-quality-20260929T1610Z/epoch-checkpoint.json'
    prior = strict_json(prior_path.read_text())
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(prior['epoch_start_utc'])
    # C127 live inventory began before its snapshot at 16:56:49 UTC. Charge
    # 660 s for the entire 16:55-17:06 admission/capture/reference envelope,
    # above its actual model process elapsed and including all live gaps.
    c127_live_upper_s = 660.0
    charged = prior['physical_charged_upper_estimate_s'] + c127_live_upper_s
    checkpoint = {'schema':'c127-epoch-checkpoint-v1', 'utc':now.isoformat(),
                  'prior_checkpoint_sha256':sha256(prior_path),
                  'epoch_start_utc':prior['epoch_start_utc'],
                  'physical_limit_s':28800, 'wall_limit_s':43200,
                  'physical_charged_upper_estimate_s':charged,
                  'physical_remaining_lower_bound_s':28800-charged,
                  'wall_remaining_s':(start+timedelta(hours=12)-now).total_seconds(),
                  'c127_live_envelope_upper_s':c127_live_upper_s,
                  'c127_model_process_elapsed_s':sum(x['elapsed_s'] for x in captures.values())+sum(x['elapsed_s'] for x in refs),
                  'raw_c127_bytes':sum(p.stat().st_size for p in raw.rglob('*') if p.is_file()),
                  'raw_limit_bytes':20*2**30}
    decision = {'schema':'c127-decision-v1',
                'status':'PASS_SLOTS40_NUMERIC_AND_SHORT_FORWARD_ADMISSION',
                'claim':'189+32 active boundary, five full logits, 36 resident FFN references under P12 slots40 E18',
                'boundary_sha256':sha256(root/'boundary-summary.json'),
                'reference_sha256':sha256(root/'reference-summary.json'),
                'captures':captures, 'reference_layers':36,
                'reference_process_elapsed_s':sum(x['elapsed_s'] for x in refs),
                'M4':'NOT_DEMONSTRATED',
                'limitations':['slots40 is a new numeric profile with changed wave geometry',
                               'full 8K/KV/attention independent validation NOT_RUN',
                               'numeric admission is not a throughput claim'],
                'next_action':'fresh two-pair C75 slots32/slots40 nominal153 operational screen under E18; do not infer speed from this probe',
                'publication':'LOCAL_ONLY', 'default_changed':False}
    manifest = {'schema':'c127-compact-manifest-v1',
                'raw_manifests':{run_id:sha256(raw/(run_id+'.json')) for run_id in RUNS}
                    | {f'c127-ref-l{layer:02d}-01':row['manifest_sha256'] for layer,row in enumerate(refs)},
                'capture_trees':{arm:row['tree'] for arm,row in captures.items()},
                'receipts_sha256':{f'c127-ref-l{layer:02d}-01':row['receipt_sha256'] for layer,row in enumerate(refs)},
                'raw_bytes':checkpoint['raw_c127_bytes']}
    return decision, checkpoint, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    decision, checkpoint, manifest = analyze(root)
    for name, value in (('decision.json',decision),('epoch-checkpoint.json',checkpoint),('manifest.json',manifest)):
        save_new(root/name,value)
    print(json.dumps({'status':decision['status'],
                      'physical_remaining_lower_bound_s':checkpoint['physical_remaining_lower_bound_s']}))


if __name__ == '__main__':
    main()
