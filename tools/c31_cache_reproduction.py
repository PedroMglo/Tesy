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

SPECS = (('c31-d1-prefix2048', 'on', 'D1', 1),
         ('c31-d2-prefix2048', 'on', 'D2', 2),
         ('c31-d3-prefix2048', 'on', 'D3', 3))
SPEC_BY_ID = {spec[0]:spec for spec in SPECS}
REQUESTS = ('c31-first-turn2048', 'c31-second-turn128')
ORIGINAL_FROZEN = c24.frozen


def workload(root):
    row = strict_json((root/'bridge-input.json').read_text())
    if row != {'schema':'c31-bridge-input-v1',
               'context_intro':'Context: ', 'prefix_words':1960,
               'increment_words':127, 'question':'\nReply with exactly OK.',
               'max_tokens':256, 'first_prompt_range':[1980,2100],
               'second_prompt_range':[2100,2500],
               'min_common_prefix_ids':1900}:
        raise GateError('C31 prospective bridge input changed')
    return row


def install_hooks():
    c24.workload = workload
    c24.REQUESTS = REQUESTS
    c24.SPEC = SPECS
    c24.frozen = frozen
    c24.validate_arm = validate_arm


def frozen(root, spec):
    run_id=spec[0]
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
    command=config['server_command']
    if command[command.index('-lv')+1] != '3' or config['explicit_env']:
        raise GateError('C31 diagnostic logging base changed')
    command[command.index('-lv')+1]='4'
    config['explicit_env']={'LLAMA_SERVER_SLOTS_DEBUG':'1'}
    protocol['campaign_id']='tesy-c31-session-bridge-20260927'
    protocol['protocol_id']=run_id+'-v1'
    protocol['c24']['mode']='synthetic-two-turn-chat-bridge'
    protocol['c24']['prefix_runner_sha256']=sha256(__file__)
    protocol['c24']['claim']='instrumented cache-path diagnostic only; no timing promotion'
    protocol['c31']={'parent_c27_decision_sha256':sha256(
            Path('results/c27-session-bridge-20260927T2220Z/decision.json')),
        'parent_c28_failure_sha256':sha256(
            Path('results/c28-conversation-bridge-20260927T2237Z/decision.json')),
        'parent_c29_failure_sha256':sha256(
            Path('results/c29-conversation-bridge-20260927T2252Z/decision.json')),
        'parent_c30_decision_sha256':sha256(
            Path('results/c30-cache-diagnostic-20260927T2314Z/decision.json')),
        'diagnostic_env':{'LLAMA_SERVER_SLOTS_DEBUG':'1'},
        'diagnostic_log_verbosity':4,
        'max_fresh_process_runs':3,
        'next_run_only_if_all_previous_cache_gates_pass':True,
        'timing_promotable':False,
        'assistant_message_sha256':sha256(root/'assistant-message.json'),
        'assistant_message_digest':digest(assistant),
        'first_turn_must_match_before_second':True,
        'second_user_words':127,
        'minimum_ordered_common_prefix_ids':1900,
        'cache_upper_bound':'min(second prompt IDs, first prompt IDs + first completion tokens), from server slot.prompt.tokens',
        'first_final_content_nullable':True}
    config['suite']='c31diagnostic'
    protocol['identity']['config_sha256']=digest(config)
    protocol['identity']['input_sha256']['assistant-message.json']=sha256(root/'assistant-message.json')
    return protocol,config,tasks,row


def validate_conversation_cache(first_prompt_n, second_prompt_n,
                                first_completion_n, common, cache_n, processed_n):
    values=(first_prompt_n,second_prompt_n,first_completion_n,common,cache_n,processed_n)
    if any(type(x) is not int or x<0 for x in values) or \
       first_prompt_n<=0 or second_prompt_n<=0 or first_completion_n<=0 or \
       common>first_prompt_n or common>second_prompt_n or \
       not max(0,common-32)<=cache_n<=min(second_prompt_n,first_prompt_n+first_completion_n) or \
       cache_n+processed_n!=second_prompt_n:
        raise GateError('C31 conversation cache accounting outside source-derived bounds')


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
        raise GateError('C31 official tokenizer ID set invalid')
    common=0
    for a,b in zip(ids[REQUESTS[0]],ids[REQUESTS[1]]):
        if a!=b: break
        common+=1
    if common<1900:
        raise GateError('C31 two-turn ordered common prefix too short')
    results=raw['results']; first,second=results
    assistant=strict_json((root/'assistant-message.json').read_text())
    if digest(first['message'])!=digest(assistant) or first['timings']['cache_n']!=0:
        raise GateError('C31 generated turn/cache differs from frozen conversation')
    validate_conversation_cache(len(ids[REQUESTS[0]]),len(ids[REQUESTS[1]]),
                                first['usage']['completion_tokens'],common,
                                second['timings']['cache_n'],second['timings']['prompt_n'])
    for result in results:
        if result['usage']['prompt_tokens']!=len(ids[result['id']]) or \
           result['usage']['completion_tokens']<=0 or result['usage']['completion_tokens']>256 or \
           result.get('stream_metrics',{}).get('done_observed') is not True or \
           type(result['stream_metrics'].get('first_text_chunk_s')) not in (int,float):
            raise GateError('C31 conversation token/stream completeness invalid')
    return 'PASS_BRIDGE',maxima,cpu,server_gate,common,ids


def physical_budget(root):
    prior_idle=sum(strict_json(p.read_text())['duration_s'] for p in
                   Path('results').glob('c*-*/**/*-idle.json') if root not in p.parents)
    if program_physical_consumed()+prior_idle+3*(900+1850)>16*3600:
        raise GateError('physical execution budget cannot cover C31 bridge')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path)
    p.add_argument('--freeze',action='store_true')
    p.add_argument('--run',choices=SPEC_BY_ID)
    p.add_argument('--measurement-commit')
    args=p.parse_args()
    root=args.root
    install_hooks()
    if args.freeze:
        hashes={}
        for spec in SPECS:
            protocol,_,_,_=frozen(root,spec)
            path=root/'protocols'/f'{spec[0]}.json'
            with path.open('x') as out:
                json.dump(protocol,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
            hashes[spec[0]]=sha256(path)
        print(json.dumps({'status':'FROZEN','protocol_sha256':hashes}))
        return
    if args.run:
        run_id=args.run
        spec=SPEC_BY_ID[run_id]
        if not args.measurement_commit or git('rev-parse','HEAD')!=args.measurement_commit or \
           git('status','--porcelain'):
            raise GateError('C31 measurement commit/worktree not frozen')
        for previous in SPECS[:SPEC_BY_ID[run_id][3]-1]:
            prior=strict_json((root/f'{previous[0]}-receipt.json').read_text())
            if prior['status']!='PASS_BRIDGE':
                raise GateError('C31 subsequent diagnostic requires every previous cache gate PASS')
        physical_budget(root)
        result=c24.run_arm(root,spec,args.measurement_commit)
        receipt=strict_json((root/f'{run_id}-receipt.json').read_text())
        summary={'schema':'c31-cache-path-diagnostic-v1','run_id':run_id,
                 'status':receipt['status'],'measurement_commit':args.measurement_commit,
                 'receipt_sha256':sha256(root/f'{run_id}-receipt.json'),
                 'actual_common_prefix_ids':receipt['actual_common_prefix_ids'],
                 'results':receipt['results'],
                 'claim_limit':'slots-debug/trace instrumented; no production timing or full M3/M4 claim'}
        with (root/f'{run_id}-diagnostic.json').open('x') as out:
            json.dump(summary,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
        print(json.dumps({'status':receipt['status'],'requests':len(receipt['results'])}))
        if result:
            raise SystemExit(result)
        return
    p.error('choose --freeze or --run')


if __name__=='__main__':
    main()
