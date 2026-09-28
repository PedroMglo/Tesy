#!/usr/bin/env python3
"""Preserve C47's first ON runtime assertion and mark the repeat NOT_RUN."""

import json
from datetime import datetime, timezone
from pathlib import Path

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from run_bounded import sha256


ROOT = Path('results/c47-skip-boundary-20260928T0927Z')
INDEX = Path('results/120b-program-index.json')


def read(path):
    return strict_json(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    outputs = [ROOT/name for name in ('decision.json','resource-summary.json','manifest.json','boundary-summary.json')]
    if any(path.exists() for path in outputs):
        raise GateError('C47 closure is no-replace')
    off_id, on_id, repeat_id = ('c47-g2-off01','c47-g2-on01','c47-g2-on02')
    off = read(ROOT/f'{off_id}-receipt.json')
    on = read(ROOT/f'{on_id}-receipt.json')
    off_raw = read(ROOT/'raw'/f'{off_id}.json')
    on_raw = read(ROOT/'raw'/f'{on_id}.json')
    error = (ROOT/'raw'/f'{on_id}.stderr').read_text()
    if off['status'] != 'PASS_CAPTURE_SCOPE' or off_raw['returncode'] != 0 or \
       on['returncode'] != -6 or on_raw['stop_reason'] is not None or \
       'ggml-backend.cpp:584: GGML_ASSERT(device) failed' not in error or \
       (ROOT/f'{repeat_id}-receipt.json').exists() or \
       (ROOT/'raw'/f'{repeat_id}.json').exists():
        raise GateError('C47 failure identity/classification differs')
    for raw in (off_raw,on_raw):
        cg = raw['cgroup_end']
        if cg['swap_current'] or cg['events']['oom'] or cg['events']['oom_kill']:
            raise GateError('C47 unexpected cgroup swap/OOM')
    idle_total = sum(read(path)['duration_s'] for path in Path('results').glob('c*-*/**/*-idle.json'))
    used = program_physical_consumed()+idle_total+2400
    decision = {
        'schema':'c47-decision-v1','status':'FAIL_RESOURCES_OR_EVIDENCE',
        'specific_failure':'RUNTIME_ASSERT_CPU_BUFFER_TYPE_DEVICE_NULL',
        'measurement_commit':off['measurement_commit'],
        'backend_commit':read(ROOT/'protocol.json')['backend_commit'],
        'off':{'run_id':off_id,'status':off['status'],'elapsed_s':off['elapsed_s']},
        'on':{'run_id':on_id,'status':'FAIL_OTHER_RUNTIME_ASSERT',
              'returncode':on['returncode'],'elapsed_s':on['elapsed_s'],
              'stderr_sha256':sha256(ROOT/'raw'/f'{on_id}.stderr')},
        'on_fresh_repeat':{'run_id':repeat_id,'status':'NOT_RUN_AFTER_FIRST_ON_FAIL'},
        'source_cause':'ggml_backend_cpu_buffer_type has NULL device by design; C47 called ggml_backend_dev_type on that NULL; no prefill output was produced',
        'same_profile_fidelity':'NOT_RUN_DUE_RUNTIME_ASSERT',
        'canonical_reference':'NOT_RUN', 'timing':'NOT_RUN',
        'old_failures_preserved':['C43 profiler prelaunch FAIL','C44 profiler prelaunch FAIL',
                                  'C41b telemetry FAIL','C9-C17 CPU95 thermal FAILs'],
        'physical_budget_consumed_s':used,
        'physical_budget_remaining_s':16*3600-used,
        'next_action':'C48 new identity: use ggml_backend_buffer_is_host for CPU execution eligibility, new source commit/build/operator test/preflight and contemporary OFF/ON/ON captures; no C47 retry',
        'M3':'PARTIAL','M4':'NOT_RUN','default_changed':False,
        'closed_utc':datetime.now(timezone.utc).isoformat(),
    }
    resource = {'schema':'c47-resource-summary-v1','status':'NO_RESOURCE_GUARD_FAILURE_BEFORE_ASSERT',
                'off_maxima':off['maxima'],'on_maxima':on['maxima'],
                'off_cgroup_end':off_raw['cgroup_end'],
                'on_cgroup_end':on_raw['cgroup_end'],
                'on_start':on['idle']['end'],
                'limit':'ON ended by source assertion before numeric output; no performance/thermal claim'}
    raw_paths = [ROOT/'raw'/f'{run_id}{suffix}' for run_id in (off_id,on_id)
                 for suffix in ('.json','.stdout','.stderr','.samples.jsonl')]
    manifest = {'schema':'c47-manifest-v1','measurement_commit':off['measurement_commit'],
                'compact_sha256':{path.name:sha256(path) for path in
                                  (ROOT/'protocol.json',ROOT/'preflight.json',
                                   ROOT/f'{off_id}-receipt.json',ROOT/f'{on_id}-receipt.json')},
                'raw_sha256':{str(path):sha256(path) for path in raw_paths if path.exists()}}
    boundary = {'schema':'c47-boundary-summary-v1','status':'FAIL_RESOURCES_OR_EVIDENCE',
                'specific_failure':decision['specific_failure'],
                'off_capture':'PASS_CAPTURE_SCOPE','on_capture':'ABORT_BEFORE_PREFILL',
                'on_repeat':'NOT_RUN','numeric_comparisons':0}
    write_new(outputs[0],decision)
    write_new(outputs[1],resource)
    write_new(outputs[2],manifest)
    write_new(outputs[3],boundary)
    with (ROOT/'LEDGER.md').open('a') as stream:
        stream.write('\n- OFF run passed capture in 71.895 s. First ON aborted after 15.817 s before prefill at `GGML_ASSERT(device)`; CPU buffer type has NULL device. Cgroup swap/OOM zero; no thermal guard failure.\n')
        stream.write('- ON fresh repeat, bitwise comparison, canonical reference and timing NOT_RUN. C47 FAIL preserved; new C48 identity required for the buffer-type correction.\n')
    index = read(INDEX)
    index['units'].append({'identity':'c47','root':str(ROOT),'status':decision['status'],
                           'specific_failure':decision['specific_failure']})
    index['next_action'] = decision['next_action']
    index['updated_utc'] = decision['closed_utc']
    temp = INDEX.with_suffix('.json.tmp')
    with temp.open('x') as stream:
        json.dump(index,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    temp.replace(INDEX)
    print(json.dumps({'status':decision['status'],'specific_failure':decision['specific_failure'],
                      'remaining_physical_s':decision['physical_budget_remaining_s']}))


if __name__ == '__main__':
    main()
