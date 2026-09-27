#!/usr/bin/env python3
"""Bounded two-turn 8K chat bridge with the prior assistant turn frozen."""

import argparse
import json
from pathlib import Path

import c24_session_bridge as c24
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c18_cpu_telemetry import summarize_samples
from c8_observer_runner import program_physical_consumed
from c9_server_admission import digest, git, validate_receipt
from run_bounded import sha256

RUN_ID = 'c28-g1-prefix2048'
SPEC = (RUN_ID, 'on', 'G1', 1)
REQUESTS = ('c28-first-turn2048', 'c28-second-turn128')
ORIGINAL_FROZEN = c24.frozen


def workload(root):
    row = strict_json((root/'bridge-input.json').read_text())
    if row != {'schema':'c28-bridge-input-v1',
               'context_intro':'Context: ', 'prefix_words':1960,
               'increment_words':127, 'question':'\nReply with exactly OK.',
               'max_tokens':256, 'first_prompt_range':[1980,2100],
               'second_prompt_range':[2100,2500],
               'min_common_prefix_ids':1900}:
        raise GateError('C28 prospective bridge input changed')
    return row


def install_hooks():
    c24.workload = workload
    c24.REQUESTS = REQUESTS
    c24.SPEC = (SPEC,)
    c24.frozen = frozen
    c24.validate_arm = validate_arm


def frozen(root, spec):
    protocol,config,tasks,row=ORIGINAL_FROZEN(root,spec)
    assistant = strict_json((root/'assistant-message.json').read_text())
    prior = strict_json((Path('results/c27-session-bridge-20260927T2220Z')/
                         'c27-g1-prefix2048-receipt.json').read_text())
    if assistant.get('role') != 'assistant' or \
       digest(assistant) != prior['results'][0]['message_sha256'] or \
       prior['status'] != 'PASS_BRIDGE':
        raise GateError('frozen synthetic assistant turn differs from C27 PASS')
    tasks[0][1]['expected_message_sha256'] = digest(assistant)
    tasks[1][1]['messages'] = [tasks[0][1]['messages'][0], assistant,
                               {'role':'user', 'content':' beta'*row['increment_words']+
                                row['question']}]
    config['token_id_relationships'] = []
    protocol['campaign_id']='tesy-c28-session-bridge-20260927'
    protocol['protocol_id']=RUN_ID+'-v1'
    protocol['c24']['mode']='synthetic-two-turn-chat-bridge'
    protocol['c24']['prefix_runner_sha256']=sha256(__file__)
    protocol['c24']['claim']='one bounded generated-assistant two-turn bridge; no 20-request or quality claim'
    protocol['c28']={'parent_c27_decision_sha256':sha256(
            Path('results/c27-session-bridge-20260927T2220Z/decision.json')),
        'assistant_message_sha256':sha256(root/'assistant-message.json'),
        'assistant_message_digest':digest(assistant),
        'first_turn_must_match_before_second':True,
        'second_user_words':127,
        'minimum_ordered_common_prefix_ids':1900,
        'first_final_content_nullable':True}
    config['suite']='c28bridge'
    protocol['identity']['config_sha256']=digest(config)
    protocol['identity']['input_sha256']['assistant-message.json']=sha256(root/'assistant-message.json')
    return protocol,config,tasks,row


def validate_arm(root, spec, protocol, config, raw):
    run_id = spec[0]
    samples=[strict_json(line) for line in
             (root/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
    maxima=validate_receipt(protocol,config,raw,samples,root,run_id=run_id,
                            protocol_filename=f'protocols/{run_id}.json',expected_results=2)
    cpu=summarize_samples(samples,require_safe=True)
    normalized=strict_json((root/'raw'/f'{run_id}.normalized.json').read_text())
    server_gate=validate_c2(normalized,{name:protocol[name] for name in PROTOCOL})
    ids=strict_json((root/'raw'/f'{run_id}.tokenization.json').read_text())
    if set(ids)!=set(REQUESTS) or any(type(x) is not int for values in ids.values() for x in values):
        raise GateError('C28 official tokenizer ID set invalid')
    common=0
    for a,b in zip(ids[REQUESTS[0]],ids[REQUESTS[1]]):
        if a!=b: break
        common+=1
    if common<1900:
        raise GateError('C28 two-turn ordered common prefix too short')
    results=raw['results']; first,second=results
    assistant=strict_json((root/'assistant-message.json').read_text())
    if digest(first['message'])!=digest(assistant) or first['timings']['cache_n']!=0 or \
       not common-32<=second['timings']['cache_n']<=common:
        raise GateError('C28 generated turn/cache differs from frozen conversation')
    for result in results:
        if result['usage']['prompt_tokens']!=len(ids[result['id']]) or \
           result['usage']['completion_tokens']<=0 or result['usage']['completion_tokens']>256 or \
           result.get('stream_metrics',{}).get('done_observed') is not True or \
           type(result['stream_metrics'].get('first_text_chunk_s')) not in (int,float):
            raise GateError('C28 conversation token/stream completeness invalid')
    return 'PASS_BRIDGE',maxima,cpu,server_gate,common,ids


def physical_budget(root):
    prior_idle=sum(strict_json(p.read_text())['duration_s'] for p in
                   Path('results').glob('c*-*/**/*-idle.json') if root not in p.parents)
    if program_physical_consumed()+prior_idle+900+1850>16*3600:
        raise GateError('physical execution budget cannot cover C28 bridge')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path)
    p.add_argument('--freeze',action='store_true')
    p.add_argument('--run',action='store_true')
    p.add_argument('--measurement-commit')
    args=p.parse_args()
    root=args.root
    install_hooks()
    if args.freeze:
        protocol,_,_,_=frozen(root,SPEC)
        path=root/'protocols'/f'{RUN_ID}.json'
        with path.open('x') as out:
            json.dump(protocol,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
        print(json.dumps({'status':'FROZEN','protocol_sha256':sha256(path)}))
        return
    if args.run:
        if not args.measurement_commit or git('rev-parse','HEAD')!=args.measurement_commit or \
           git('status','--porcelain'):
            raise GateError('C28 measurement commit/worktree not frozen')
        physical_budget(root)
        result=c24.run_arm(root,SPEC,args.measurement_commit)
        receipt=strict_json((root/f'{RUN_ID}-receipt.json').read_text())
        summary={'schema':'c28-streaming-bridge-summary-v1','run_id':RUN_ID,
                 'status':receipt['status'],'measurement_commit':args.measurement_commit,
                 'receipt_sha256':sha256(root/f'{RUN_ID}-receipt.json'),
                 'actual_common_prefix_ids':receipt['actual_common_prefix_ids'],
                 'results':receipt['results'],
                 'claim_limit':'synthetic two-turn chat with exact frozen assistant response; one process, two requests; no sustained/quality M3/M4'}
        with (root/'bridge-summary.json').open('x') as out:
            json.dump(summary,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
        print(json.dumps({'status':receipt['status'],'requests':len(receipt['results'])}))
        if result:
            raise SystemExit(result)
        return
    p.error('choose --freeze or --run')


if __name__=='__main__':
    main()
