"""Prospective R0/R2 utility, with the full population and actual validation clock."""
import argparse
import json
import math
import statistics
import time
from pathlib import Path
from c131_holdout_grade import grade

METRICS = ('first_final_s', 'cold_first_final_s', 'completion_s', 'validated_s', 'prefix_preparation_s',
           'cold_prefill_s', 'incremental_prefill_s', 'decode_seconds_per_native_output')


def positive(x):
    return type(x) in (int, float) and math.isfinite(x) and x > 0


def validate(v, spec, profile, case):
    if (v.get('status') != 'COMPLETE_FREE_NATIVE_UTILITY_OBSERVATION' or v.get('profile') != profile
        or v.get('case') != case or v.get('official_input_ids') != spec['ids']
        or v.get('provided_messages') != spec['task']['messages']
        or v.get('cache_prefix_n') != len(spec['ids']) - 153 or v.get('evaluated_n') != 153
        or v.get('cap') != 768 or v.get('deadline_s') != 360):
        raise ValueError('official inputs/profile/call contract incomplete')
    if not 2000 <= len(spec['ids']) <= 2600 or any(type(x) is not int or not 0 <= x < 201088 for x in spec['ids']):
        raise ValueError('official2K input IDs invalid')
    ids, events = v.get('native_output_ids'), v.get('events')
    if type(ids) is not list or any(type(x) is not int or not 0 <= x < 201088 for x in ids):
        raise ValueError('native output IDs missing/invalid')
    if type(events) is not list or len(events) != len(ids) or v.get('output_count_including_eog') != len(ids):
        raise ValueError('output/event accounting missing')
    finish = v.get('finish_reason')
    if finish not in ('stop', 'length', 'deadline') or len(ids) > 768:
        raise ValueError('finish/accounting invalid')
    if finish == 'stop' and (not ids or not events[-1].get('terminal_eog')):
        raise ValueError('natural stop not witnessed')
    if finish == 'length' and len(ids) != 768:
        raise ValueError('output cap not witnessed')
    if any(e.get('native_id') != t or type(e.get('terminal_eog')) is not bool or not positive(e.get('observed_s')) for t, e in zip(ids, events)):
        raise ValueError('native event evidence invalid')
    if any(e.get('terminal_eog') for e in events[:-1]):
        raise ValueError('generation continued beyond EOG')
    if any(b['observed_s'] < a['observed_s'] for a, b in zip(events, events[1:])):
        raise ValueError('event clock regressed')
    for k in ('prefix_preparation_s', 'incremental_prefill_s', 'cold_prefill_s', 'completion_s', 'request_start_monotonic_s', 'completion_monotonic_s'):
        if not positive(v.get(k)): raise ValueError('invalid clock ' + k)
    if not math.isclose(v['cold_prefill_s'], v['prefix_preparation_s'] + v['incremental_prefill_s'], abs_tol=1e-7):
        raise ValueError('overlapping prefill phases')
    if type(v.get('decode_s')) not in (int, float) or not math.isfinite(v['decode_s']) or v['decode_s'] < 0:
        raise ValueError('decode clock invalid')
    if not math.isclose(v['completion_s'], v['incremental_prefill_s'] + v['decode_s'], abs_tol=1e-7):
        raise ValueError('exclusive phase clocks inconsistent')
    if not math.isclose(v['completion_monotonic_s'] - v['request_start_monotonic_s'], v['completion_s'], abs_tol=1e-7):
        raise ValueError('request monotonic clock inconsistent')
    if finish == 'deadline' and v['completion_s'] < 360:
        raise ValueError('deadline not witnessed')
    if events and events[-1]['observed_s'] > v['completion_s']:
        raise ValueError('event outside request')
    for k in ('first_reasoning_s', 'first_final_s', 'cold_first_final_s'):
        if v.get(k) is not None and (not positive(v[k]) or (k != 'cold_first_final_s' and v[k] > v['completion_s'])):
            raise ValueError('first content clock invalid')
    if not all(isinstance(v.get(k), str) for k in ('raw_generated_text', 'reasoning', 'final', 'native_parser_error')):
        raise ValueError('full response text missing')
    if v['final'] and v['first_final_s'] is None and not v['native_parser_error']:
        raise ValueError('final lacks first-final evidence')
    n = len(ids)
    if n:
        if not positive(v.get('decode_seconds_per_native_output')) or not math.isclose(v['decode_seconds_per_native_output'], v['decode_s'] / n, abs_tol=1e-9):
            raise ValueError('native per-output convention inconsistent')
    elif v.get('decode_seconds_per_native_output') is not None or finish != 'deadline':
        raise ValueError('unexposed/missing outputs cannot be positive evidence')
    if type(v.get('decode_forward_calls')) is not int or v['decode_forward_calls'] < 0 or v['decode_forward_calls'] > n:
        raise ValueError('decode forwards invalid')
    for name in ('initial', 'final_state'):
        state = v.get(name, {})
        if state.get('pending_queue') != 0 or [l.get('layer') for l in state.get('layers', [])] != list(range(36)):
            raise ValueError('complete drained state missing')
        for layer in state['layers']:
            if any(len(layer.get(k, [])) != 40 for k in ('slot_expert', 'slot_state', 'slot_generation', 'slot_claimed')) or any(layer['slot_claimed']) or any(x not in (0, 2) for x in layer['slot_state']):
                raise ValueError('resident state incomplete')
    return v


def classify(v, graded, validator_begin, validator_end):
    if not math.isfinite(validator_begin) or not math.isfinite(validator_end) or validator_begin < v['completion_monotonic_s'] or validator_end < validator_begin:
        raise ValueError('actual validation clock invalid')
    if graded.get('status') not in ('PASS', 'FAIL'):
        raise ValueError('validator environment/evidence invalid')
    good = v['finish_reason'] == 'stop' and not v['native_parser_error'] and graded['status'] == 'PASS' and v['completion_s'] <= 360
    outcome = 'SUCCESS' if good else {'length': 'OUTPUT_CAP', 'deadline': 'DEADLINE_CENSORED'}.get(v['finish_reason'], 'WRONG_FINAL')
    return dict(measurement_valid=True, functional_success=good, outcome=outcome, grader=graded,
                metrics={**{k: v[k] for k in METRICS if k != 'validated_s'},
                         'validated_s': validator_end - v['request_start_monotonic_s'] if good else None},
                validator_duration_s=validator_end - validator_begin,
                completion_to_validator_s=validator_begin - v['completion_monotonic_s'],
                validation_end_monotonic_s=validator_end,
                note='validated time includes actual process cleanup/supervisor delay; failures have null latency, no zero imputation')


def paired(rows):
    if len(rows) != 4 or [r['profile'] for r in rows] != ['A', 'B', 'B', 'A'] or len({r['id'] for r in rows}) != 4:
        raise ValueError('exact ordered ABBA population required')
    if any(r['assessment'].get('measurement_valid') is not True for r in rows):
        raise ValueError('invalid measurement in population')
    for r in rows:
        s = r['assessment']
        if s.get('outcome') not in ('SUCCESS','OUTPUT_CAP','WRONG_FINAL','DEADLINE_CENSORED') or type(s.get('functional_success')) is not bool or (s['outcome']=='SUCCESS') != s['functional_success']:
            raise ValueError('outcome/success inconsistent')
        if s['functional_success'] and any(not positive(s.get('metrics',{}).get(k)) for k in METRICS):
            raise ValueError('successful metric missing/nonfinite/zero')
    pairs = []
    for ai, bi in ((0, 1), (3, 2)):
        a, b = rows[ai], rows[bi]
        if a['observation']['official_input_ids'] != b['observation']['official_input_ids'] or a['observation']['provided_messages'] != b['observation']['provided_messages']:
            raise ValueError('provided inputs/history differ')
        for k in ('layers', 'n_calls', 'pending_queue'):
            if a['observation']['initial'][k] != b['observation']['initial'][k]:
                raise ValueError('complete prepared resident state differs')
        both = a['assessment']['functional_success'] and b['assessment']['functional_success']
        gains = {}
        for k in METRICS:
            va, vb = a['assessment']['metrics'][k], b['assessment']['metrics'][k]
            gains[k] = 100 * (va - vb) / va if both and positive(va) and positive(vb) else None
        pairs.append(dict(A=a['id'], B=b['id'], gain_percent=gains, both_success=both,
                          A_outcome=a['assessment']['outcome'], B_outcome=b['assessment']['outcome'],
                          native_outputs_equal=a['observation']['native_output_ids'] == b['observation']['native_output_ids']))
    med = {k: statistics.median([p['gain_percent'][k] for p in pairs]) if all(p['gain_percent'][k] is not None for p in pairs) else None for k in METRICS}
    passed = all(p['both_success'] for p in pairs) and med['first_final_s'] >= 8 and all(p['gain_percent']['first_final_s'] > 0 for p in pairs) and all(med[k] >= -5 for k in METRICS if k != 'first_final_s')
    return dict(status='GO_CLASS_UTILITY_SCREEN' if passed else 'NO_GO_CLASS_UTILITY_SCREEN', pairs=pairs,
                median_paired_gain_percent=med, population=[dict(id=r['id'],profile=r['profile'],outcome=r['assessment']['outcome'],functional_success=r['assessment']['functional_success']) for r in rows])


def main():
    p = argparse.ArgumentParser(); p.add_argument('directory', type=Path); p.add_argument('--fixture', type=Path); p.add_argument('--profile'); p.add_argument('--case'); p.add_argument('--family', action='store_true'); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.family:
        protocol = json.loads((a.directory / 'protocol.json').read_text()); classes = {}
        cases=protocol['freeze_contract']['cases']
        if len(protocol['runs']) != 8 or len({r['id'] for r in protocol['runs']}) != 8 or len(cases) != 2 or len(set(cases)) != 2 or any(r['case'] not in cases for r in protocol['runs']): raise ValueError('exact eight-arm two-class family required')
        for case in protocol['freeze_contract']['cases']:
            rows = []
            for run in protocol['runs']:
                if run['case'] != case: continue
                bounded=json.loads((a.directory/'raw'/(run['id']+'.json')).read_text())
                if bounded.get('run_id')!=run['id'] or bounded.get('returncode')!=0 or bounded.get('stop_reason') or bounded.get('mapped_libraries_match_ldd') is not True or bounded.get('backend_libraries_sha256')!=protocol['binary_libraries']:
                    raise ValueError('bounded identity/resource/evidence failure')
                obs = json.loads((Path(run['command'][4]) / 'result.json').read_text())
                spec = json.loads(Path(run['command'][2]).read_text())[case]
                validate(obs, spec, run['profile'], case)
                assessment = json.loads(Path(run['post_run_command'][-1]).read_text())
                rows.append(dict(id=run['id'],profile=run['profile'],observation=obs,assessment=assessment))
            classes[case] = paired(rows)
        out = dict(status='GO_TWO_CLASS_NATIVE_UTILITY_SCREEN' if all(v['status'] == 'GO_CLASS_UTILITY_SCREEN' for v in classes.values()) else 'NO_GO_TWO_CLASS_NATIVE_UTILITY_SCREEN', classes=classes,
                   scope='Constructed native near2K warm153, fixed provided history, free greedy responses. R2 own profile; not server integration, stochastic exactness, full8K or M4.')
    else:
        spec = json.loads(a.fixture.read_text())[a.case]
        v = validate(json.loads((a.directory / 'result.json').read_text()), spec, a.profile, a.case)
        begin = time.monotonic()
        graded = grade(spec['task']['grader'], v['final']) if v['finish_reason'] == 'stop' and not v['native_parser_error'] else dict(status='FAIL',reason='no complete natural parsed final')
        out = classify(v, graded, begin, time.monotonic())
    with a.output.open('x') as f: json.dump(out, f, indent=2, allow_nan=False); f.write('\n')
    print(out.get('status', out.get('outcome')))


if __name__ == '__main__': main()
