#!/usr/bin/env python3
"""Prospective 8K streaming bridge using C25c's observed tokenizer boundary."""

import argparse
import json
from pathlib import Path

import c24_session_bridge as c24
from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed
from c9_server_admission import digest, git
from run_bounded import sha256

RUN_ID = 'c27-g1-prefix2048'
SPEC = (RUN_ID, 'on', 'G1', 1)
REQUESTS = ('c27-prefix2048', 'c27-increment128')
ORIGINAL_FROZEN = c24.frozen


def workload(root):
    row = strict_json((root/'bridge-input.json').read_text())
    if row != {'schema':'c27-bridge-input-v1',
               'context_intro':'Context: ', 'prefix_words':1960,
               'increment_words':127, 'question':'\nReply with exactly OK.',
               'max_tokens':256, 'first_prompt_range':[1980,2100],
               'second_prompt_range':[2108,2228],
               'min_common_prefix_ids':1900}:
        raise GateError('C27 prospective bridge input changed')
    return row


def install_hooks():
    c24.workload = workload
    c24.REQUESTS = REQUESTS
    c24.SPEC = (SPEC,)
    c24.frozen = frozen


def frozen(root, spec):
    protocol,config,tasks,row=ORIGINAL_FROZEN(root,spec)
    protocol['campaign_id']='tesy-c27-session-bridge-20260927'
    protocol['protocol_id']=RUN_ID+'-v1'
    protocol['c24']['mode']='synthetic-streaming-2048-prefix-bridge-corrected-input'
    protocol['c24']['prefix_runner_sha256']=sha256(__file__)
    protocol['c24']['claim']='one bounded official +128-ID 8K streaming bridge; no full M3/M4/quality claim'
    protocol['c27']={'parent_c24_failure_sha256':sha256(
        Path('results/c24-session-bridge-20260927T2136Z/decision.json')),
        'parent_c25c_diagnostic_sha256':sha256(
        Path('results/c25c-token-diagnostic-20260927T2156Z/decision.json')),
        'parent_c26_failure_sha256':sha256(
            Path('results/c26-session-bridge-20260927T2205Z/decision.json')),
        'fixture_change':'same generated text as C26; only the tested SSE null parser repair differs',
        'first_final_content_nullable':True}
    config['suite']='c27bridge'
    protocol['identity']['config_sha256']=digest(config)
    return protocol,config,tasks,row


def physical_budget(root):
    prior_idle=sum(strict_json(p.read_text())['duration_s'] for p in
                   Path('results').glob('c*-*/**/*-idle.json') if root not in p.parents)
    if program_physical_consumed()+prior_idle+900+1850>16*3600:
        raise GateError('physical execution budget cannot cover C27 bridge')


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
            raise GateError('C27 measurement commit/worktree not frozen')
        physical_budget(root)
        result=c24.run_arm(root,SPEC,args.measurement_commit)
        receipt=strict_json((root/f'{RUN_ID}-receipt.json').read_text())
        summary={'schema':'c27-streaming-bridge-summary-v1','run_id':RUN_ID,
                 'status':receipt['status'],'measurement_commit':args.measurement_commit,
                 'receipt_sha256':sha256(root/f'{RUN_ID}-receipt.json'),
                 'actual_common_prefix_ids':receipt['actual_common_prefix_ids'],
                 'results':receipt['results'],
                 'claim_limit':'synthetic growing prompt, one process, two requests; no full M3/M4'}
        with (root/'bridge-summary.json').open('x') as out:
            json.dump(summary,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
        print(json.dumps({'status':receipt['status'],'requests':len(receipt['results'])}))
        if result:
            raise SystemExit(result)
        return
    p.error('choose --freeze or --run')


if __name__=='__main__':
    main()
