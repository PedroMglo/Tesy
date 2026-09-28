#!/usr/bin/env python3
"""Bounded 4096+128 exact-prefix server bridge with fixed template date."""

import argparse
from pathlib import Path
import json

import c24_session_bridge as c24
from c2_gate import GateError, strict_json
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import configuration, digest, git
from run_bounded import backend_library_hashes, sha256


ROOT = Path('results/c36-prefix4096-20260928T0153Z')
BACKEND = Path('/tmp/tesy-c35-backend-20260928')
BINARY = BACKEND/'build-c35-gcc15/bin/llama-server'
SPEC = (('c36-prefix4096-bridge','on','G1',1),)
REQUESTS = ('c36-prefix4096','c36-increment128')


def workload(root):
    row=strict_json((root/'bridge-input.json').read_text())
    expected={'schema':'c36-bridge-input-v1','context_intro':'Context: ',
              'prefix_words':3960,'increment_words':128,
              'question':'\nReply with exactly OK.','max_tokens':256,
              'first_prompt_range':[3980,4120],
              'second_prompt_range':[4108,4248],
              'min_common_prefix_ids':3900}
    if row!=expected:
        raise GateError('C36 workload differs from freeze')
    return row


def overall(root):
    row=strict_json((root/'protocol.json').read_text())
    if row['schema']!='c36-prefix4096-protocol-v1' or \
            row['backend_commit']!=git('-C',str(BACKEND),'rev-parse','HEAD') or \
            git('-C',str(BACKEND),'status','--porcelain') or \
            sha256('results/c35b-template-date-20260928T0122Z/decision.json')!=row['parent_c35b_decision_sha256'] or \
            any(sha256(root/name)!=h for name,h in row['input_sha256'].items()) or \
            model_stat()!=strict_json((root/'preflight.json').read_text())['model']['stat']:
        raise GateError('C36 source/input/model identity changed')
    return row


def frozen(root,spec):
    run_id,arm,phase,order=spec
    top=overall(root)
    protocol,config=configuration(root)
    if config['server_command'][config['server_command'].index('-ngl')+1]!='8':
        raise GateError('C36 P8 source configuration changed')
    config['server_command'][0]=str(BINARY)
    config['server_command'][config['server_command'].index('-ngl')+1]='12'
    config.update(backend_root=str(BACKEND),suite='c36bridge',arm=arm,
                  task_ids=list(REQUESTS),n_ctx=8192,pretokenize=True,
                  freeze_token_ids=True,allow_cache_prompt=True,
                  enforce_output_reserve=True,
                  prompt_token_ranges={REQUESTS[0]:workload(root)['first_prompt_range'],
                                       REQUESTS[1]:workload(root)['second_prompt_range']},
                  token_id_relationships=[{'first':REQUESTS[0],'second':REQUESTS[1],
                                           'expected_delta':128,'min_common':3900}],
                  stream_requests=True,
                  request_policy={'mode':'synthetic-4096-prefix-bridge','attempts':1,
                                  'max_tokens':256,'temperature':0,'seed':42,
                                  'per_request_timeout_s':top['timeouts_s']['per_request']},
                  total_timeout_s=top['timeouts_s']['process'])
    libraries=backend_library_hashes(str(BINARY),BACKEND)
    if not libraries:
        raise GateError('C36 backend libraries missing')
    protocol['identity'].update(backend_sha=top['backend_commit'],
                                binary_sha256=sha256(BINARY),
                                library_sha256=libraries,
                                config_sha256=digest(config),
                                workload_sha256=sha256(root/'bridge-input.json'),
                                input_sha256=dict(top['input_sha256'],
                                                  **{'protocol.json':sha256(root/'protocol.json')}))
    protocol.update(campaign_id='tesy-c36-prefix4096-20260928',
                    protocol_id=run_id+'-v1',expected_request_ids=list(REQUESTS))
    protocol['limits']['cpu_max_c']=100
    protocol['c24']=protocol.pop('c9')
    protocol['c24'].update(mode='synthetic-4096-prefix-bridge',n_gpu_layers=12,
                           arm=arm,phase=phase,order=order,
                           prefix_runner_sha256=sha256(__file__),
                           idle_max_start_c=[50,50,45],
                           idle_match_tolerance_c=[5,5,3],
                           claim='one bounded 4096+128 prefix bridge; no true conversation, sustained or quality claim')
    protocol['c18']={'thermal_monitor':'CPU95 warning, CPU100/explicit cooling/clock collapse stop'}
    protocol['c36']={'fixed_template_date':top['frozen_template_date'],
                     'backend_tree':git('-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
                     'runner_sha256':sha256(__file__),
                     'timing_promotable':False}
    row=workload(root)
    prompts=(c24.prompt_text(row,0),c24.prompt_text(row,row['increment_words']))
    tasks=[(key,{'id':key,'category':'synthetic-session-bridge',
                 'messages':[{'role':'user','content':prompt}],
                 'cache_prompt':True,
                 'chat_template_kwargs':{'tesy_template_date':top['frozen_template_date']}})
           for key,prompt in zip(REQUESTS,prompts)]
    return protocol,config,tasks,row


def install_hooks():
    c24.workload=workload
    c24.REQUESTS=REQUESTS
    c24.SPEC=SPEC
    c24.frozen=frozen


def physical_budget():
    idle=sum(strict_json(path.read_text())['duration_s'] for path in
             Path('results').glob('c*-*/**/*-idle.json'))
    if program_physical_consumed()+idle+900+2000+120>16*3600:
        raise GateError('C36 physical budget insufficient')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze',action='store_true')
    mode.add_argument('--run',action='store_true')
    parser.add_argument('--measurement-commit')
    args=parser.parse_args()
    root=args.root
    if root!=ROOT or not (root/'raw').is_dir() or not (root/'protocols').is_dir():
        raise GateError('C36 output root changed')
    install_hooks()
    if args.freeze:
        protocol,_,_,_=frozen(root,SPEC[0])
        with (root/'protocols'/f'{SPEC[0][0]}.json').open('x') as out:
            json.dump(protocol,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
        print(json.dumps({'status':'FROZEN','protocol_sha256':sha256(root/'protocols'/f'{SPEC[0][0]}.json')}))
        return 0
    if not args.measurement_commit or git('rev-parse','HEAD')!=args.measurement_commit or \
            git('status','--porcelain'):
        raise GateError('C36 measurement commit/worktree not frozen')
    physical_budget()
    return c24.run_arm(root,SPEC[0],args.measurement_commit)


if __name__=='__main__':
    raise SystemExit(main())
