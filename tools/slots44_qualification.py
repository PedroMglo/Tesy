"""Post-C225 40/44 utility contract over the existing C2 lifecycle.

The historical H2 evaluator/trajectory rule is deliberately not changed.
"""
import argparse
import copy
import json
import math
import os
from pathlib import Path
from statistics import median

import passive_wait_natural as prior
import native64_natural as runner
from native64_numeric import read, save, git, BACKEND
from passive_wait_utility import JSON_ID, PROTECTED, task_loss
from parallel_runtime import parallel_environment
from run_bounded import sha256
from c2_gate import GateError
from host_resource_policy import validate_resource_protocol

IDS = tuple(prior.old.IDS) + (JSON_ID,)
DEADLINES = (120, 60, 120, 180)
PROTECTIONS = PROTECTED + ('JSON_first_final_s', 'JSON_seconds_per_output')
SOURCES = tuple(dict.fromkeys(prior.SOURCES + ('tools/slots44_qualification.py',)))


def finite(value, positive=True):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise GateError('invalid finite metric')
    return value


def derived(row, expected_profile, expected_ids, expected_run_id=None):
    """Reject flattering scalars lacking the exact underlying request population."""
    if row.get('measurement_valid') is not True:
        raise GateError('INVALID_MEASUREMENT')
    if row.get('profile') != expected_profile or (expected_run_id and row.get('run_id') != expected_run_id):
        raise GateError('wrong arm/profile/order')
    if row.get('slots') != (40 if expected_profile == 'A' else 44) or row.get('ubatch') != 32:
        raise GateError('wrong numerical profile')
    if row.get('input_ids') != expected_ids or row.get('nominal153') is not True:
        raise GateError('INCONCLUSIVE_INPUT_OR_PREFIX')
    reqs = row.get('requests')
    if type(reqs) is not list or len(reqs) != 4 or [x.get('id') for x in reqs] != list(IDS):
        raise GateError('request cardinality/order/identity')
    if len(set(expected_ids)) != 4 or any(type(v) is not list or not v or any(type(n) is not int or n < 0 for n in v) for v in expected_ids.values()):
        raise GateError('official ID arrays invalid')
    values = {}
    for i, req in enumerate(reqs):
        loss = task_loss(req, DEADLINES[i])
        if finite(req.get('L')) != loss:
            raise GateError('loss differs from receipt timestamps/outcome')
        if req.get('functional_success') is True:
            if req.get('outcome') != 'SUCCESS' or loss >= 1:
                raise GateError('invalid successful outcome')
            t = req.get('native_timings', {})
            sm = req.get('stream_metrics', {})
            tr = req.get('trajectory', {})
            if tr.get('finish_reason') != 'stop' or not sm.get('done_observed'):
                raise GateError('successful response not naturally complete')
            if t.get('cache_n', -1) + t.get('prompt_n', -1) != len(expected_ids[IDS[i]]):
                raise GateError('token accounting inconsistent')
            if i == 1 and (t['cache_n'], t['prompt_n']) != (2044, 153):
                raise GateError('nominal153 accounting differs')
            tag = ('cold', 'T2', 'SQL', 'JSON')[i]
            values[tag + '_first_final_s'] = finite(req.get('first_final_s'))
            values[tag + '_completion_s'] = finite(req.get('completion_s'))
            values[tag + '_seconds_per_output'] = finite(t.get('predicted_ms')) / 1000 / finite(t.get('predicted_n'))
            if i == 0:
                values['cold_prefill_s'] = finite(t.get('prompt_ms')) / 1000
            if i == 1:
                values['incremental_prefill_s'] = finite(t.get('prompt_ms')) / 1000
        if i in (2, 3):
            values[('SQL_L', 'JSON_L')[i - 2]] = loss
    values['U'] = (values['SQL_L'] + values['JSON_L']) / 2
    for key, value in values.items():
        if row.get(key) != value:
            raise GateError('scalar differs from request receipt: ' + key)
    return values


def pair_metrics(a, b, expected_ids, run_ids=None):
    av = derived(a, 'A', expected_ids, run_ids[0] if run_ids else None)
    bv = derived(b, 'B', expected_ids, run_ids[1] if run_ids else None)
    successes = all(r['functional_success'] is True for r in a['requests'] + b['requests'])
    gains = {k: 100 * (av[k] - bv[k]) / av[k] for k in ('SQL_L', 'JSON_L', 'U')}
    protections = {k: 100 * (av[k] - bv[k]) / av[k] if k in av and k in bv else None for k in PROTECTIONS}
    return {'gains': gains, 'protections': protections, 'all_functional_success': successes}


def evaluate(pairs, expected_ids, order):
    if len(pairs) != 3 or len(order) != 6 or [v for _, v in order] != list('ABBAAB') or len({k for k, _ in order}) != 6:
        return {'status': 'INCONCLUSIVE_INCOMPLETE_OR_WRONG_PAIRS'}
    expected_pairs = ((order[0][0], order[1][0]), (order[3][0], order[2][0]), (order[4][0], order[5][0]))
    try:
        details = [pair_metrics(a, b, expected_ids, names) for (a, b), names in zip(pairs, expected_pairs)]
    except (GateError, KeyError, TypeError, ValueError) as exc:
        return {'status': 'INCONCLUSIVE_INVALID_MEASUREMENT', 'reason': str(exc)}
    gains = {k: [p['gains'][k] for p in details] for k in ('SQL_L', 'JSON_L', 'U')}
    protections = {k: [p['protections'][k] for p in details] for k in PROTECTIONS}
    success = all(p['all_functional_success'] for p in details)
    primary = all(median(gains[k]) >= threshold and all(x > 0 for x in gains[k]) for k, threshold in [('SQL_L', 8), ('JSON_L', 5), ('U', 5)])
    protected = all(all(v is not None for v in vals) and median(vals) >= -5 and min(vals) >= -15 for vals in protections.values())
    return {'status': 'GO_CONFIRMATION' if success and primary and protected else 'NO_GO_NEW_SLOTS44_UTILITY_QUALIFICATION',
            'paired_gains': gains, 'medians': {k: median(v) for k, v in gains.items()},
            'protected_gains': protections, 'protected_medians': {k: median(v) if all(x is not None for x in v) else None for k, v in protections.items()},
            'all_functional_success': success, 'missing_not_zero': True,
            'scope': 'Provided identical histories; free responses of distinct numerical profiles; not equal FLOPs'}


def futility(a, b, expected_ids):
    details = pair_metrics(a, b, expected_ids)
    if not details['all_functional_success']:
        return 'FUNCTIONAL_FAILURE_PREVENTS_LATENCY_QUALIFICATION'
    for key, value in details['gains'].items():
        if value <= 0:
            return 'PRIMARY_NONPOSITIVE:' + key
    for key, value in details['protections'].items():
        if value is None or value < -15:
            return 'INDIVIDUAL_PROTECTION:' + key
    return None


def analyze(root, rid, profile, p, config):
    row = prior.analyze(root, rid, profile, p, config)
    row.update(slots=40 if profile == 'A' else 44, ubatch=32)
    command = config['server_command']
    if command[command.index('--moe-stream-cache') + 1] != str(row['slots']) + 's' or command[command.index('-ub') + 1] != '32':
        raise GateError('effective slots/ubatch mismatch')
    if 'GOMP_SPINCOUNT' in config['explicit_env'] or p['parallel_runtime']['environment']['values'].get('GOMP_SPINCOUNT') is not None:
        raise GateError('unexpected passive-wait treatment')
    expected = read(root/'workload.json')['official_ids']
    derived(row, profile, expected, rid)
    return row


def freeze(root, epoch):
    root = root.resolve(); epoch = epoch.resolve()
    if (root/'protocol.json').exists() or (root/'freeze-manifest.json').exists():
        raise GateError('freeze already published; no replacement')
    root.mkdir(exist_ok=True); (root/'raw').mkdir(exist_ok=True); (root/'protocols').mkdir(exist_ok=True)
    if not (root/'.gitignore').exists(): (root/'.gitignore').write_text('raw/\nbuild/\n')
    def preparation_save(path,value):
        if path.exists():
            if read(path)!=value: raise GateError('incomplete preparation differs')
        else: save(path,value)
    cap = read(epoch/'reuse-and-capacity.json')['cap_bytes']
    for n in ('snapshot.json', 'resource-policy.json'):
        preparation_save(root/n, read(epoch/n))
    preparation_save(root/'session-input.json', read(prior.old.PRIOR/'session-input.json'))
    w = read(runner.base.REPO/'results/c223-passive-wait-confirmation-20261001/workload.json')
    if runner.server.digest(w) != runner.server.digest(prior.workload()):
        raise GateError('frozen unopened JSON/workload bytes no longer correspond')
    w = copy.deepcopy(w)
    # Official holdout IDs are frozen by vocab-only renderer before first forward.
    w['official_ids'][JSON_ID] = read(epoch/'official-json-input.json')['ids']
    save(root/'workload.json', w)
    order = [(root.name.split('-')[0] + f'-{i+1}-{v}', v) for i, v in enumerate('ABBAAB')]
    protocol = {'schema': 'post-c225-slots44-qualification-v1', 'epoch': str(epoch), 'hypothesis': 'H1', 'confirmation': True,
                'cap_bytes': cap, 'order': order, 'maximum_live_s': 3600, 'arm_maximum_s': 600,
                'unit_runtime_max_s': 595, 'remaining_reserved_live_s': 2650, 'remaining_reserved_raw_bytes': 256*2**20,
                'source_sha256': {k: sha256(runner.base.REPO/k) for k in SOURCES}, 'workload_sha256': sha256(root/'workload.json'),
                'gate': {'SQL_gain_percent': 8, 'JSON_gain_percent': 5, 'U_gain_percent': 5, 'all_positive': True,
                         'all_tasks_success_both': True, 'protection_median_min': -5, 'protection_pair_min': -15},
                'deadline_s': list(DEADLINES), 'validator_budget_s': 2, 'server_timeout_s': 525,
                'futility': 'Only after complete pair: functional failure, primary<=0, protection<-15',
                'claim': 'Supplied transcript identical; free trajectories may differ across40/44', 'no_retry': True, 'publication': 'LOCAL_ONLY'}
    save(root/'protocol.json', protocol)
    runner.base.CAP = cap
    for rid, profile in order:
        p, c = prior.old.make(root, rid, profile, 'H1', True, cap_bytes=cap)
        if p['resources']['cgroup']['memory_max_bytes'] != cap:
            raise GateError('source adapter cap differs from sole frozen authority')
        c.update(suite='slots44qualification', task_ids=list(IDS), total_timeout_s=525, require_natural_stop=True,
                 prospective_task_outcomes=True, expected_official_token_ids=w['official_ids'],
                 per_task_request_policy={k: {'max_tokens': [256,256,384,512][i], 'per_request_timeout_s': DEADLINES[i]} for i,k in enumerate(IDS)},
                 prompt_token_ranges={k: [1900,6500] for k in IDS})
        p['expected_request_ids'] = list(IDS); p['portfolio']['source_sha256'] = protocol['source_sha256']; p['identity']['config_sha256'] = runner.server.digest(c)
        validate_resource_protocol(p)
        save(root/'protocols'/(rid+'.json'), p); save(root/(rid+'-config.json'), c)
    save(root/'freeze-manifest.json', {'sha256': {str(p.relative_to(root)): sha256(p) for p in root.rglob('*.json')}, 'created_at': runner.now(), 'no_hash_of_own_commit': True})


def hooks(root):
    p=read(root/'protocol.json'); w=read(root/'workload.json')
    def completed_pair(a,b):
        index=next(i+1 for i,n in enumerate((0,3,4)) if p['order'][n][0]==a['run_id'])
        details=pair_metrics(a,b,w['official_ids'])
        reason=futility(a,b,w['official_ids'])
        save(root/f'completed-pair-{index}.json',dict(details,A=a['run_id'],B=b['run_id'],futility=reason,
             no_missing_pair_median=True))
        return reason
    return {'cap': p['cap_bytes'], 'suite': 'slots44qualification', 'tasks': prior.tasks, 'checker': prior.checker,
            'analyze': analyze, 'arm_script': 'tools/slots44_qualification.py',
            'evaluate': lambda pairs: evaluate(pairs, w['official_ids'], p['order']),
            'futility_after_pair': completed_pair,
            'accept_terminal_censor': prior.terminal_censor_allowed}


if __name__ == '__main__':
    q=argparse.ArgumentParser(); q.add_argument('mode', choices=('freeze','arm','family')); q.add_argument('root', type=Path)
    q.add_argument('--epoch', type=Path); q.add_argument('--run-id'); q.add_argument('--measurement-head'); a=q.parse_args()
    if a.mode=='freeze': freeze(a.root,a.epoch)
    elif a.mode=='arm': raise SystemExit(runner.arm(a.root,a.run_id,a.measurement_head,hooks=hooks(a.root.resolve())))
    else: raise SystemExit(runner.family(a.root,hooks=hooks(a.root.resolve())))
