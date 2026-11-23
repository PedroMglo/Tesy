#!/usr/bin/env python3
"""Preserve C49 idle-only admission block without implying a model failure."""

import json
from datetime import datetime, timezone
from pathlib import Path

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256


ROOT = Path('results/c49-assistant-history-20260928T1021Z')
INDEX = Path('results/120b-program-index.json')


def save(path, obj):
    with Path(path).open('x') as out:
        json.dump(obj, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def main():
    receipt = strict_json((ROOT/'c49-p12-assistant-history01-receipt.json').read_text())
    idle = receipt['idle']
    if receipt['status'] != 'THERMAL_PREFLIGHT_BLOCKED' or \
       idle['duration_s'] < 900 or any((ROOT/'raw').iterdir()) or \
       sha256(ROOT/'thermal-series.jsonl') != idle['series_sha256']:
        raise GateError('C49 idle-only block evidence differs')
    used = program_physical_consumed() + sum(
        strict_json(path.read_text())['duration_s']
        for path in Path('results').glob('c*-*/**/*-idle.json')) + 2400
    next_action = ('C50 new identity: same P12 server/session/model/backend/input and E18/CPU100 guards; '
                   'prospectively admit idle CPU/GPU/NVMe <=55/55/50 C for 300 contiguous seconds, '
                   'then execute the two-turn assistant-history gate once')
    decision = {'schema':'c49-decision-v1','status':'THERMAL_PREFLIGHT_BLOCKED',
                'measurement_commit':receipt['measurement_commit'],
                'run_id':receipt['run_id'],'model_loaded':False,'requests':'NOT_RUN',
                'idle_duration_s':idle['duration_s'],'idle_start':idle['start'],
                'idle_end':idle['end'],'idle_last60_trend_c':idle['last60_trend_c'],
                'idle_band_c':idle['max_start_c'],
                'idle_series_sha256':idle['series_sha256'],
                'resource_guard_violation':False,
                'old_failures_preserved':['C47 runtime assertion','C48 same-profile mismatch',
                                          'C9-C17 CPU95 protocol thermal FAILs'],
                'physical_budget_consumed_s':used,
                'physical_budget_remaining_s':16*3600-used,
                'next_action':next_action,'M3':'PARTIAL','M4':'NOT_RUN',
                'default_changed':False,'closed_utc':datetime.now(timezone.utc).isoformat()}
    summary = {'schema':'c49-resource-summary-v1','status':'IDLE_ONLY',
               'sample_count':idle['sample_count'],
               'max_gap_s':idle['max_gap_overall_s'],
               'series_sha256':idle['series_sha256'],
               'limit':'no full-model process or server response'}
    manifest = {'schema':'c49-manifest-v1','measurement_commit':receipt['measurement_commit'],
                'compact_sha256':{name:sha256(ROOT/name) for name in
                                  ('protocol.json','preflight.json',
                                   'c49-p12-assistant-history01-idle.json',
                                   'c49-p12-assistant-history01-receipt.json')},
                'raw_sha256':{'thermal-series.jsonl':idle['series_sha256']}}
    save(ROOT/'decision.json',decision)
    save(ROOT/'resource-summary.json',summary)
    save(ROOT/'manifest.json',manifest)
    with (ROOT/'LEDGER.md').open('a') as out:
        out.write(f'\n- Idle admission {idle["duration_s"]:.3f} s ended THERMAL_PREFLIGHT_BLOCKED under the frozen <=50 C CPU band; no model loaded, requests NOT_RUN. No absolute guard violation.\n')
        out.write('- C50 will prospectively use <=55 C idle CPU while keeping CPU100 stop and all other guards. C48 numeric FAIL remains separate.\n')
    index = strict_json(INDEX.read_text())
    index['units'].append({'identity':'c49','root':str(ROOT),'status':decision['status'],
                           'model_loaded':False})
    index['next_action'] = next_action
    index['updated_utc'] = decision['closed_utc']
    temp = INDEX.with_suffix('.json.tmp')
    with temp.open('x') as out:
        json.dump(index,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    temp.replace(INDEX)
    print(json.dumps({'status':decision['status'],
                      'remaining_physical_s':decision['physical_budget_remaining_s']}))


if __name__ == '__main__':
    main()
