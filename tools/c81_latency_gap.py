#!/usr/bin/env python3
"""Retrospective C52b per-request latency arithmetic, with C74 probe context."""
import json
import math
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256

REPO = Path(__file__).resolve().parents[1]
C52 = REPO / 'results/c52b-assistant-history-sustained-20260928T1132Z'
C74 = REPO / 'results/c74-wave-confirm-20260928T1740Z'
ROOT = REPO / 'results/c81-session-latency-gap-20260928T1942Z'
RUN = 'c52b-p12-assistant-history01'


def verified(root, manifest_name, entry):
    manifest = strict_json((root / manifest_name).read_text())
    file = root / entry
    record = manifest['raw_sha256'][file.name]
    if file.stat().st_size != record['size_bytes'] or sha256(file) != record['sha256']:
        raise GateError('C52b raw hash/size mismatch')
    return strict_json(file.read_text()),sha256(file)


def main():
    raw,raw_sha = verified(C52, 'manifest.json', Path('raw') / (RUN+'.json'))
    decision = strict_json((C52/'decision.json').read_text())
    if decision['completed_requests'] != 20 or len(raw['results']) != 20 or \
       decision['M3'] != 'SESSION_MECHANICS_20_REQUEST_70_MIN_TESTED_SCOPE_LATENCY_OPEN':
        raise GateError('C52b complete session prerequisite changed')
    c74_manifest = strict_json((C74/'manifest.json').read_text())
    c74_file = C74/'timing-pairs.json'
    if sha256(c74_file) != c74_manifest['timing_pairs_sha256']:
        raise GateError('C74 compact timing hash changed')
    c74 = strict_json(c74_file.read_text())
    rows=[]
    for i,r in enumerate(raw['results']):
        if r['id'] != f'c52b-turn{i:02d}' or r['finish_reason'] != 'stop' or \
           not r['stream_metrics']['done_observed'] or \
           not isinstance(r['stream_metrics']['first_final_content_chunk_s'],(int,float)):
            raise GateError('C52b request completion differs')
        if i == 0:continue
        prefill=r['timings']['prompt_ms']/1000
        first_final=r['stream_metrics']['first_final_content_chunk_s']
        decode_tps=r['timings']['predicted_per_second']
        residual=first_final-prefill
        if not all(math.isfinite(x) and x>0 for x in (prefill,first_final,decode_tps,residual)):
            raise GateError('C52b latency value invalid')
        rows.append({'request_id':r['id'],'new_prompt_tokens':r['timings']['prompt_n'],
                     'prefill_s':prefill,'first_final_s':first_final,
                     'held_fixed_post_prefill_residual_s':residual,
                     'decode_tok_s':decode_tps,
                     'completion_tokens':r['usage']['completion_tokens']})
    if len(rows)!=19:
        raise GateError('C52b incremental count incomplete')
    med={key:median(row[key] for row in rows)
         for key in ('prefill_s','first_final_s','held_fixed_post_prefill_residual_s','decode_tok_s')}
    gap={'decode_tpot_reduction_needed_percent':100*(1-med['decode_tok_s']/6),
         'post_prefill_reduction_needed_with_zero_prefill_percent':
             100*(1-10/med['held_fixed_post_prefill_residual_s']),
         'zero_prefill_residual_over_10_count':sum(row['held_fixed_post_prefill_residual_s']>10
                                                   for row in rows)}
    result={'schema':'c81-session-latency-gap-v1','status':'PREFILL_ONLY_INSUFFICIENT_HELD_FIXED',
        'evidence_class':'INFERIDO_FROM_C52b_AND_C74_MEASURED_INPUTS',
        'hypothesis_sha256':sha256(ROOT/'hypothesis.json'),
        'C52b_raw_sha256':raw_sha,'C52b_manifest_sha256':sha256(C52/'manifest.json'),
        'C74_timing_pairs_sha256':sha256(c74_file),
        'C74_manifest_sha256':sha256(C74/'manifest.json'),
        'incremental_request_count':len(rows),'medians':med,'target_gap':gap,
        'C74_probe_median_pair_gain_percent':{
            case:c74['cases'][case]['median_pair_gain_percent']
            for case in ('cold513','warm154')},
        'rows':rows,
        'interpretation':'Under fixed per-request post-prefill residual, zero prefill alone leaves all 19 incremental first-final times above 10 s. C74 probe gains are not server gains.',
        'limits':['SSE client first-content and server prefill are duration measures from different instrumentation paths',
                  'arithmetic residual is not a physical lower bound after a runtime/profile change',
                  'C52b synthetic repeated-answer session, not diverse quality suite',
                  'C74 teacher-forced probe does not measure exact-prefix server TTFT'],
        'next_discriminant':'After C75 8K numeric/session gate, measure phase-specific expert demand, cache hit/miss and exposed wait on exact-prefix server decode; simulate bounded RAM L2 before implementation.'}
    ROOT.mkdir(exist_ok=True)
    with (ROOT/'gap-analysis.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
    print(json.dumps({'status':result['status'],'medians':med,'target_gap':gap}))


if __name__=='__main__':
    main()
