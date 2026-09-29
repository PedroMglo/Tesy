#!/usr/bin/env python3
"""Strict, model-free phase subtraction for the observed C114 session."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from c2_gate import GateError, strict_json


REPO=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value,label):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise GateError(f'{label} must be finite numeric')
    return float(value)


def run(protocol_path,out_path):
    p=strict_json(protocol_path.read_text())
    if p.get('schema')!='c115-decode-goal-bound-protocol-v1':
        raise GateError('C115 protocol schema invalid')
    paths={name:REPO/rel for name,rel in p['inputs'].items()}
    for name,path in paths.items():
        if not path.is_file() or sha(path)!=p['input_sha256'][name]:
            raise GateError(f'C115 {name} hash missing/changed')
    raw=strict_json(paths['c114_candidate_raw'].read_text())
    manifest=strict_json(paths['c114_manifest'].read_text())
    if manifest['files']['c114-p1-candidate.json']['sha256']!=sha(paths['c114_candidate_raw']):
        raise GateError('C115 candidate raw not bound to manifest')
    decision=strict_json(paths['c114_decision'].read_text())
    if decision['status']!='INCOMPLETE_MATCH_NOT_ADMITTED' or len(raw['results'])!=2:
        raise GateError('C115 C114 classification/results invalid')
    cold,increment=raw['results']
    if increment['finish_reason']!='stop' or \
       increment['timings']['prompt_n']!=153 or \
       increment['timings']['cache_n']!=2044 or \
       increment['usage']['completion_tokens']!=47:
        raise GateError('C115 incremental workload changed')
    first=finite(increment['stream_metrics']['first_final_content_chunk_s'],'first final')
    prompt=finite(increment['timings']['prompt_ms'],'prompt_ms')/1000
    decode=finite(increment['timings']['predicted_ms'],'predicted_ms')/1000
    tok_s=finite(increment['timings']['predicted_per_second'],'predicted_per_second')
    if not 0<prompt<first or not 0<decode or not 0<tok_s:
        raise GateError('C115 phase durations invalid')
    target_final=finite(p['targets']['first_final_s'],'target first final')
    target_tps=finite(p['targets']['decode_tok_s'],'target decode tok/s')
    residual=first-prompt
    c111=strict_json(paths['c111_timing'].read_text())
    if c111['status']!='TWO_DIAGNOSTIC_PAIRS_COMPLETE' or len(c111['pairs'])!=2:
        raise GateError('C115 C111 pair evidence invalid')
    c108=strict_json(paths['c108_analysis'].read_text())
    if c108['trace_validation']['status']!='PASS':
        raise GateError('C115 corrected trace gate invalid')
    result={
      'schema':'c115-decode-goal-bound-v1',
      'evidence_class':'INFERRED_CONDITIONAL_FROM_MEASURED_PHASES',
      'input_sha256':p['input_sha256'],
      'workload':{'prompt_new_ids':153,'cache_n':2044,'completion_tokens':47,
                  'profile':'C114 C75 ON P12/8K medium synthetic actual-history; one run'},
      'observed':{'first_final_s':first,'prompt_s':prompt,'predicted_decode_s':decode,
                  'decode_tok_s':tok_s},
      'targets':p['targets'],
      'conditional_fixed_decode':{
          'first_final_if_prompt_zero_s':residual,
          'still_above_10s_by_s':residual-target_final,
          'remaining_decode_phase_reduction_needed_percent_if_prompt_zero':
              100*max(0,residual-target_final)/residual,
          'total_first_final_reduction_needed_percent':100*(first-target_final)/first,
          'decode_time_per_token_reduction_needed_percent_for_target_tps':
              100*(1-tok_s/target_tps),
          'assumption':'subtract measured prompt phase from first-final wall; hold the rest of the same request unchanged; no claim of physically realizable zero prompt'},
      'c111':{'prefill_median_paired_gain_percent':c111['median_paired_gain_percent']['prefill_s'],
              'decode_median_paired_gain_percent':c111['median_paired_gain_percent']['decode_s'],
              'late_decode_pair_gains_percent':[x['gain_percent']['step65_192_s'] for x in c111['pairs']]},
      'c108_trace_limit':'C105 189+32 instrumented waits are a different workload and incomplete wait coverage; do not divide them by C114 latency',
      'decision':'PREFILL_ONLY_INSUFFICIENT_UNDER_FIXED_DECODE_FOR_OBSERVED_C114_REQUEST',
      'limits':['single C114 candidate run, no paired server gain','phase subtraction conditional, not a causal intervention',
                'C111 is teacher-forced 2009+192, not free server generation',
                'C108 L2 demand-byte savings are not latency savings'],
      'next_discriminant':'capture a bounded warm153 server request with request/phase/position and slot-queue/read/H2D/compute intervals, plus overhead-neutrality bridge; keep medium/P12/8K and exact routing'
    }
    with out_path.open('x') as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False)
        f.write('\n')
    print(json.dumps({'decision':result['decision'],'first_final_if_prompt_zero_s':residual,
                      'decode_reduction_needed_percent':result['conditional_fixed_decode']['decode_time_per_token_reduction_needed_percent_for_target_tps']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('protocol',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    run(args.protocol,args.output)
