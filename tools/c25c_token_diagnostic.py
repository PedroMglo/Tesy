#!/usr/bin/env python3
"""One bounded, no-generation official-tokenizer diagnosis after C24 fixture failure."""

import argparse
import json
from pathlib import Path

import c24_session_bridge as c24
from c2_gate import GateError, strict_json
from c9_server_admission import digest, git
from run_bounded import sha256

RUN_ID = 'c25c-token-diagnostic'
SPEC = (RUN_ID, 'on', 'D0', 1)
ORIGINAL_FROZEN = c24.frozen


def frozen(root, spec):
    protocol, config, tasks, row = ORIGINAL_FROZEN(root, spec)
    protocol['campaign_id'] = 'tesy-c25c-token-diagnostic-20260927'
    protocol['protocol_id'] = RUN_ID + '-v1'
    protocol['c24']['mode'] = 'tokenization-only-diagnostic'
    protocol['c24']['claim'] = 'observe frozen official token relation; no inference claim'
    protocol['c24']['prefix_runner_sha256'] = sha256(__file__)
    protocol['c25c'] = {'parent_c24_decision_sha256': sha256(
        Path('results/c24-session-bridge-20260927T2136Z/decision.json')),
        'expected_stop_reason': 'RUN_ERROR:GateError:frozen incremental token count/common prefix invalid',
        'model_outputs_permitted': False}
    config['suite'] = 'c25ctoken'
    protocol['identity']['config_sha256'] = digest(config)
    return protocol, config, tasks, row


def observe(root):
    token_file = root/'raw'/f'{RUN_ID}.tokenization.json'
    raw_file = root/'raw'/f'{RUN_ID}.json'
    token_ids = strict_json(token_file.read_text())
    raw = strict_json(raw_file.read_text())
    first, second = (token_ids[k] for k in c24.REQUESTS)
    common = 0
    for a,b in zip(first,second):
        if a != b:
            break
        common += 1
    if len(token_ids) != 2 or any(type(x) is not int or x < 0 for x in first+second) or \
       raw['results'] or raw['stop_reasons'] != [
           'RUN_ERROR:GateError:frozen incremental token count/common prefix invalid'] or \
       raw['source_sha256'].get('.tokenization.json') != sha256(token_file):
        raise GateError('C25c diagnostic raw/output/stop/provenance invalid')
    result = {'schema':'c25c-official-tokenization-diagnostic-v1',
              'status':'TOKENIZATION_DIAGNOSTIC_PASS',
              'run_id':RUN_ID,
              'measurement_commit':git('rev-parse','HEAD'),
              'first_count':len(first), 'second_count':len(second),
              'delta_count':len(second)-len(first),
              'ordered_common_prefix_count':common,
              'first_token_sha256':digest(first), 'second_token_sha256':digest(second),
              'raw_sha256':sha256(raw_file),
              'tokenization_sha256':sha256(token_file),
              'generated_requests':0, 'model_outputs':0,
              'next_action':'new identity: freeze a +128-ID input based on official observed token boundaries'}
    with (root/'diagnostic.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path)
    p.add_argument('--freeze',action='store_true')
    p.add_argument('--run',action='store_true')
    p.add_argument('--measurement-commit')
    args=p.parse_args()
    root=args.root
    c24.frozen=frozen
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
            raise GateError('C25c measurement commit/worktree not frozen')
        c24.run_arm(root,SPEC,args.measurement_commit)
        result=observe(root)
        print(json.dumps(result,sort_keys=True))
        return
    p.error('choose --freeze or --run')


if __name__=='__main__':
    main()
