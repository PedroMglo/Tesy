#!/usr/bin/env python3
"""Reconcile C135 trace and C136 trace-off control without claiming removable wait."""

import argparse
from datetime import datetime
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c122_trace_validate import validate
from c123_analyze_trace import trace_rows, summarize_spans, simulate_completed_lru
from run_bounded import sha256

REPO = Path(__file__).resolve().parents[1]
ROOT_ON = REPO / 'results/c135-slots40-warm153-trace-20260929T2205Z'
ROOT_OFF = REPO / 'results/c136-slots40-trace-neutral-20260929T2205Z'
REFERENCE = REPO / 'results/c129-slots40-confirm-20260929T1735Z'
ON = 'c135-c75-slots40-warm153'
OFF = 'c136-c75-slots40-neutral'


def read_arm(root, name, status):
    raw = root/'raw'
    receipt_path = raw/f'{name}.receipt.json'
    receipt = strict_json(receipt_path.read_text())
    data_path = raw/f'{name}.json'
    data = strict_json(data_path.read_text())
    ids_path = raw/f'{name}.tokenization.json'
    ids = strict_json(ids_path.read_text())
    if receipt['status'] != status or receipt['raw_sha256'] != sha256(data_path) or \
       receipt['model_launch_observed'] is not True or data['returncode'] != 0 or \
       data['stop_reasons'] or len(data['results']) != 2:
        raise GateError(f'{name} receipt/raw invalid')
    return receipt, data, ids


def metrics(data):
    item = data['results'][1]
    return {'warm_prefill_s': item['timings']['prompt_ms']/1000,
            'warm_decode_s': item['timings']['predicted_ms']/1000,
            'warm_decode_tok_s': item['timings']['predicted_per_second'],
            'warm_first_final_s': item['stream_metrics']['first_final_content_chunk_s'],
            'warm_output_tokens': item['usage']['completion_tokens']}


def analyze():
    on_receipt, on, on_ids = read_arm(ROOT_ON, ON, 'PASS_DIAGNOSTIC_CAPTURE')
    off_receipt, off, off_ids = read_arm(ROOT_OFF, OFF, 'PASS_TRACE_OFF_NEUTRAL')
    ref_ids = None
    for path in sorted((REFERENCE/'raw').glob('c129-p*-candidate.tokenization.json')):
        other = strict_json(path.read_text())
        if ref_ids is None: ref_ids = other
        if other != ref_ids:
            raise GateError('C129 candidate inputs disagree')
    if on_ids != off_ids or on_ids != ref_ids:
        raise GateError('C135/C136/C129 input IDs differ')
    outputs = lambda data: [(x['id'], x['message'], x['usage']['completion_tokens'], x['finish_reason'])
                            for x in data['results']]
    if outputs(on) != outputs(off) or \
       any(outputs(on) != outputs(strict_json(path.read_text())) for path in
           sorted((REFERENCE/'raw').glob('c129-p*-candidate.json'))):
        raise GateError('C135/C136/C129 outputs differ')
    trace_path = ROOT_ON/'raw'/f'{ON}.expert.trace'
    if sha256(trace_path) != on_receipt['trace_sha256']:
        raise GateError('C135 trace receipt SHA mismatch')
    parsed = validate(trace_path)
    calls = {int(i): row for i, row in parsed['calls'].items()}
    if len(calls) != 48 or \
       [(calls[i]['n_tokens'], calls[i]['first_pos'], calls[i]['last_pos']) for i in (1,2)] != \
       [(5,2044,2048),(148,2049,2196)] or \
       any((calls[i]['n_tokens'],calls[i]['first_pos'],calls[i]['last_pos']) !=
           (1,2194+i,2194+i) for i in range(3,49)):
        raise GateError('C135 traced warm153 call plan invalid')
    layers, rows = trace_rows(trace_path)
    if sorted(layers) != list(range(36)) or \
       sum(x['device']=='CPU' for x in layers.values()) != 25 or \
       sum(x['device']=='CUDA0' for x in layers.values()) != 11:
        raise GateError('C135 layer destination invalid')
    spans = summarize_spans(rows, layers)
    durations = {phase: sum(calls[i]['end_us']-calls[i]['start_us'] for i in ids)/1e6
                 for phase,ids in (('prefill',(1,2)),('decode',range(3,49)))}
    if spans['decode']['WAIT']['union_s'] > durations['decode']:
        raise GateError('C135 wait union exceeds decode call window')
    cache = {tier: {str(g): simulate_completed_lru(rows,layers,g*2**30,tier=='gpu_only')
                    for g in (1,2,3)} for tier in ('global','gpu_only')}
    on_m, off_m = metrics(on), metrics(off)
    for item in (on_m,off_m):
        if item['warm_output_tokens'] != 47 or item['warm_decode_s'] <= 0:
            raise GateError('C135/C136 warm work invalid')
    elapsed = {}
    for key, receipt in (('on',on_receipt),('off',off_receipt)):
        a,b = datetime.fromisoformat(receipt['started_utc']),datetime.fromisoformat(receipt['ended_utc'])
        if b<a:raise GateError('receipt chronology invalid')
        elapsed[key]=(b-a).total_seconds()
    return {'schema':'c135-c136-analysis-v1', 'evidence':'MEDIDO_NO_TARGET',
        'inputs_and_outputs_equal_to_all_c129_candidate_arms':True,
        'raw_sha256':{'c135_server':on_receipt['raw_sha256'],
                      'c135_trace':on_receipt['trace_sha256'],
                      'c136_server':off_receipt['raw_sha256']},
        'receipt_sha256':{'c135':sha256(ROOT_ON/'raw'/f'{ON}.receipt.json'),
                          'c136':sha256(ROOT_OFF/'raw'/f'{OFF}.receipt.json')},
        'run_elapsed_s':elapsed,
        'server':{'trace_on':on_m,'trace_off':off_m,
                  'trace_on_minus_off_decode_s':on_m['warm_decode_s']-off_m['warm_decode_s'],
                  'trace_on_minus_off_first_final_s':on_m['warm_first_final_s']-off_m['warm_first_final_s']},
        'trace':{'events':parsed['events'],'loads':parsed['loads'],
                 'decode_call_duration_s':durations['decode'],
                 'prefill_call_duration_s':durations['prefill'],
                 'spans':spans, 'layer_devices':{'CPU':25,'CUDA0':11}},
        'conditional_target':{'six_tok_s_decode_s_for_47_tokens':47/6,
            'trace_off_decode_saving_needed_s':off_m['warm_decode_s']-47/6,
            'trace_on_decode_saving_needed_s':on_m['warm_decode_s']-47/6,
            'fraction_of_trace_on_wait_if_trace_on_rest_fixed':
                (on_m['warm_decode_s']-47/6)/spans['decode']['WAIT']['union_s']},
        'fixed_stream_completed_lru':cache,
        'limitations':['Single ordered trace-on/trace-off pair; environmental order remains a confounder.',
            'Trace-on is slower; its interval fractions are diagnostic, not a calibrated production time breakdown.',
            'WAIT is observed readiness blocking, not automatically removable time.',
            'READ bytes are logical expert slabs, not NVMe controller traffic.',
            'LRU fixes primary misses and assumes free insertion; no causal speed claim.',
            'Compute and attention/KV are not independently decomposed in this trace.']}


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',type=Path)
    a=ap.parse_args()
    result=analyze()
    encoded=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if a.output:a.output.write_text(encoded)
    else:print(encoded)
