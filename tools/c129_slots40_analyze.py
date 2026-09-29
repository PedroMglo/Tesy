#!/usr/bin/env python3
"""Validate C129 fresh paired confirmation with C128's independent arm gate."""

import argparse
from datetime import datetime
import json
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256
import c128_slots40_analyze as previous
import c129_slots40_confirm as campaign


def confirm_gate(pairs):
    if len(pairs) != 3 or any(set(pair['gain_percent']) != set(previous.METRICS) for pair in pairs):
        raise GateError('C129 incomplete confirmation pairs')
    medians = {key:median(pair['gain_percent'][key] for pair in pairs)
               for key in previous.METRICS}
    if not all(pair['same_work'] for pair in pairs):
        return 'INCONCLUSIVE_OUTPUT_DIVERGENCE', medians
    go = (medians['warm_decode_s'] >= 8 and
          all(pair['gain_percent']['warm_decode_s'] > 0 for pair in pairs) and
          all(medians[key] >= -5 for key in previous.PROTECTED))
    return ('CONFIRMED_SLOTS40_NOMINAL153' if go else 'NO_GO_CONFIRM_SLOTS40_NOMINAL153'), medians


def analyze(root):
    campaign.configure()
    pre = strict_json((root/'preflight.json').read_text())
    screen = strict_json((root/'confirm-policy.json').read_text())
    policy = strict_json((root/'resource-policy.json').read_text())
    if screen != campaign.confirm_policy(root) or \
       sha256(root/'confirm-policy.json') != pre['confirm_policy_sha256'] or \
       screen['order'] != [spec[0] for spec in campaign.ORDER]:
        raise GateError('C129 frozen policy changed')
    first = strict_json((root/'raw'/(campaign.ORDER[0][0]+'.receipt.json')).read_text())
    commit = first['measurement_commit']
    if type(commit) is not str or len(commit) != 40:
        raise GateError('C129 measurement commit invalid')
    runs = [previous.arm(root,spec,commit,policy) for spec in campaign.ORDER]
    pairs = []
    for number in (1,2,3):
        control = next(x for x in runs if x['pair']==number and x['role']=='control')
        candidate = next(x for x in runs if x['pair']==number and x['role']=='candidate')
        same_work = (control['completion_tokens']==candidate['completion_tokens'] and
                     control['prompt_tokens']==candidate['prompt_tokens'] and
                     control['cached_tokens']==candidate['cached_tokens'] and
                     control['evaluated_tokens']==candidate['evaluated_tokens'] and
                     control['tokenization_sha256']==candidate['tokenization_sha256'] and
                     control['messages']==candidate['messages'])
        gains = {key:100*(control['metrics'][key]-candidate['metrics'][key])/control['metrics'][key]
                 for key in previous.METRICS}
        pairs.append({'pair':number,'control':control['run_id'],
                      'candidate':candidate['run_id'],'same_work':same_work,
                      'gain_percent':gains,
                      'start_delta_candidate_minus_control_c':
                          [b-a for a,b in zip(control['start_temperature_c'],
                                              candidate['start_temperature_c'])]})
    status, medians = confirm_gate(pairs)
    for row in runs:
        row.pop('messages')
    timing = {'schema':'c129-timing-v1','measurement_commit':commit,
              'runs':runs,'pairs':pairs,'median_paired_gain_percent':medians,
              'primary':'warm_decode_s','protected':list(previous.PROTECTED)}
    decision = {'schema':'c129-decision-v1','status':status,
                'measurement_commit':commit,'median_paired_gain_percent':medians,
                'pairs':pairs,'primary':'warm_decode_s',
                'protected':list(previous.PROTECTED),
                'M4':'NOT_DEMONSTRATED','default_changed':False,'publication':'LOCAL_ONLY',
                'prior_c128_screen_decision_sha256':sha256(
                    previous.campaign.REPO/'results/c128-slots40-nominal153-20260929T1710Z/decision.json'),
                'next_action':'qualify slots40 quality, context and diverse active session if confirmed'}
    manifest = {'schema':'c129-manifest-v1','measurement_commit':commit,
                'raw':{p.name:{'bytes':p.stat().st_size,'sha256':sha256(p)}
                       for p in sorted((root/'raw').iterdir()) if p.is_file()}}
    return timing, decision, manifest


def main():
    ap = argparse.ArgumentParser();ap.add_argument('root',type=Path)
    root = ap.parse_args().root.resolve()
    for name,row in zip(('timing-pairs.json','decision.json','manifest.json'),analyze(root)):
        campaign.c128.campaign.save_new(root/name,row)
    print(json.dumps({'status':strict_json((root/'decision.json').read_text())['status']}))


if __name__ == '__main__':
    main()
