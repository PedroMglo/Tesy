#!/usr/bin/env python3
"""Prospective two-arm GPT-OSS session-date cache diagnostic."""

import argparse
import datetime as dt
import json
from pathlib import Path

import c24_session_bridge as c24
import c29_conversation_bridge as c29
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import digest, git, validate_receipt
from c18_cpu_telemetry import summarize_samples
from run_bounded import backend_library_hashes, sha256


ROOT = Path('results/c35-template-date-20260928T0115Z')
BACKEND = Path('/tmp/tesy-c35-backend-20260928')
BINARY = BACKEND / 'build-c35-gcc15/bin/llama-server'
SPECS = (('c35-date-shift-control', 'shifted', 'G1', 1),
         ('c35-date-stable-candidate', 'stable', 'G2', 2))
REQUESTS = ('c35-first-turn2048', 'c35-second-turn128')
BY_ID = {row[0]: row for row in SPECS}


def overall(root):
    row = strict_json((root/'protocol.json').read_text())
    if row['schema'] != 'c35-template-date-protocol-v1' or \
            row['backend_candidate_commit'] != git('-C', str(BACKEND), 'rev-parse', 'HEAD') or \
            git('-C', str(BACKEND), 'status', '--porcelain') or \
            sha256('research/patches/C35-stable-template-date.patch') != row['backend_patch_sha256'] or \
            any(sha256(root/name) != expected for name, expected in row['input_sha256'].items()) or \
            model_stat() != strict_json((root/'preflight.json').read_text())['model']['stat']:
        raise GateError('C35 frozen source/input/model identity changed')
    return row


def install_hooks():
    c24.workload = c29.workload
    c24.REQUESTS = REQUESTS
    c24.SPEC = SPECS
    c24.frozen = frozen
    c24.validate_arm = validate_arm


def frozen(root, spec):
    run_id, arm, phase, order = spec
    high = overall(root)
    protocol, config, tasks, workload = c29.frozen(root, spec)
    dates = high['dates']['control' if arm == 'shifted' else 'candidate']
    for (_, task), date in zip(tasks, dates):
        task['chat_template_kwargs'] = {'tesy_template_date': date}
    config['server_command'][0] = str(BINARY)
    config['backend_root'] = str(BACKEND)
    config['suite'] = 'c35date'
    config['token_id_relationships'] = []
    config['total_timeout_s'] = high['timeouts_s']['server_process']
    config['request_policy']['per_request_timeout_s'] = high['timeouts_s']['per_request']
    libraries = backend_library_hashes(str(BINARY), BACKEND)
    if not libraries:
        raise GateError('C35 backend libraries unavailable')
    protocol['identity'].update(backend_sha=high['backend_candidate_commit'],
                                binary_sha256=sha256(BINARY),
                                library_sha256=libraries,
                                config_sha256=digest(config),
                                input_sha256=dict(protocol['identity']['input_sha256'],
                                                  **{'protocol.json':sha256(root/'protocol.json')}))
    protocol.update(campaign_id='tesy-c35-template-date-20260928',
                    protocol_id=run_id+'-v1', expected_request_ids=list(REQUESTS))
    protocol['c35'] = {'run_id':run_id,'arm':arm,'phase':phase,'order':order,
                       'dates':dates,'runner_sha256':sha256(__file__),
                       'backend_tree':git('-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
                       'date_variable_only':True,
                       'timing_promotable':False,
                       'claim':'synthetic two-turn cache mechanism only'}
    return protocol,config,tasks,workload


def validate_arm(root, spec, protocol, config, raw):
    run_id, arm, _, _ = spec
    samples = [strict_json(line) for line in
               (root/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
    maxima = validate_receipt(protocol, config, raw, samples, root, run_id=run_id,
                              protocol_filename=f'protocols/{run_id}.json', expected_results=2)
    cpu = summarize_samples(samples, require_safe=True)
    normalized = strict_json((root/'raw'/f'{run_id}.normalized.json').read_text())
    server_gate = validate_c2(normalized, {key:protocol[key] for key in PROTOCOL})
    ids = strict_json((root/'raw'/f'{run_id}.tokenization.json').read_text())
    high = overall(root)
    if set(ids) != set(REQUESTS) or [len(ids[k]) for k in REQUESTS] != high['frozen_prompt_counts'] or \
            digest(ids[REQUESTS[0]]) != high['frozen_prompt_id_sha256']['first']:
        raise GateError('C35 official first prompt identity/count differs from freeze')
    target = 'second_changed_date_hypothesis' if arm == 'shifted' else 'second_same_date'
    if digest(ids[REQUESTS[1]]) != high['frozen_prompt_id_sha256'][target]:
        raise GateError('C35 official second prompt ID SHA differs from frozen date')
    common = next((i for i,(a,b) in enumerate(zip(ids[REQUESTS[0]],ids[REQUESTS[1]]))
                   if a != b),len(ids[REQUESTS[0]]))
    results = raw['results']
    assistant = strict_json((root/'assistant-message.json').read_text())
    if digest(results[0]['message']) != digest(assistant) or \
            results[0]['timings']['cache_n'] != 0 or \
            any(x['usage']['prompt_tokens'] != len(ids[x['id']]) or
                not 0 < x['usage']['completion_tokens'] <= 256 or
                x.get('stream_metrics',{}).get('done_observed') is not True
                for x in results):
        raise GateError('C35 conversation output/count/completion differs from freeze')
    cache = results[1]['timings']['cache_n']
    if arm == 'shifted':
        if common != 35 or cache != 35:
            raise GateError('C35 shifted-date cache did not reproduce first mismatch')
    elif common != len(ids[REQUESTS[0]]) or \
            not common-32 <= cache <= min(len(ids[REQUESTS[1]]),
                                          len(ids[REQUESTS[0]])+results[0]['usage']['completion_tokens']):
        raise GateError('C35 stable-date cache outside frozen prefix band')
    return 'PASS_BRIDGE',maxima,cpu,server_gate,common,ids


def physical_budget(root):
    idle = sum(strict_json(p.read_text())['duration_s'] for p in
               Path('results').glob('c*-*/**/*-idle.json'))
    if program_physical_consumed()+idle+2*(900+1800+120)>16*3600:
        raise GateError('C35 physical budget insufficient for both arms and cleanup')


def save_new(path, value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze',action='store_true')
    mode.add_argument('--run',choices=BY_ID)
    parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    root=args.root
    if root != ROOT or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C35 output root changed')
    install_hooks()
    if args.freeze:
        for spec in SPECS:
            protocol,_,_,_ = frozen(root,spec)
            save_new(root/'protocols'/f'{spec[0]}.json',protocol)
        print(json.dumps({'status':'FROZEN','run_ids':[x[0] for x in SPECS]}))
        return 0
    if not args.measurement_commit or git('rev-parse','HEAD') != args.measurement_commit or \
            git('status','--porcelain'):
        raise GateError('C35 measurement commit/worktree not frozen')
    if args.run == SPECS[1][0]:
        prior=strict_json((root/f'{SPECS[0][0]}-receipt.json').read_text())
        if prior['status'] != 'PASS_BRIDGE':
            raise GateError('C35 shifted-date control did not pass')
    physical_budget(root)
    rc=c24.run_arm(root,BY_ID[args.run],args.measurement_commit)
    receipt=strict_json((root/f'{args.run}-receipt.json').read_text())
    summary={'schema':'c35-date-run-summary-v1','run_id':args.run,'arm':BY_ID[args.run][1],
             'status':receipt['status'],'measurement_commit':args.measurement_commit,
             'receipt_sha256':sha256(root/f'{args.run}-receipt.json'),
             'cache_n':receipt['results'][1]['timings']['cache_n'] if len(receipt.get('results',[]))==2 else None,
             'common_prefix_ids':receipt['actual_common_prefix_ids'],
             'maxima':receipt['maxima'],'cpu_diagnostics':receipt['cpu_diagnostics'],
             'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    save_new(root/f'{args.run}-summary.json',summary)
    return rc


if __name__=='__main__':
    raise SystemExit(main())
