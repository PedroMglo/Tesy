"""Separate fixed-input timing from natural useful latency; no output selection."""
from statistics import median
from c2_gate import GateError

def paired(a,b):
    if type(a) not in (float,int) or type(b) not in (float,int) or not 0<a< float('inf') or not 0<b<float('inf'):raise GateError('invalid paired timing')
    return 100*(a-b)/a

def evaluate(pairs,regime,confirmation=False):
    if regime not in ('W','S'):raise GateError('unfrozen regime')
    if len(pairs)!=(3 if confirmation else 2):raise GateError('pair cardinality')
    metrics=('prefill153_s','decode32_s','prefix_prepare_s') if regime=='W' else ('T2_first_final_s','SQL_validated_s','cold_prefill_s','cold_first_final_s','T2_completion_s','T3_first_final_s','incremental_prefill_s','decode_seconds_per_reported_output')
    gains={k:[] for k in metrics};divergent=False
    for a,b in pairs:
        if (a['profile'],b['profile'])!=('A32','B64'):raise GateError('wrong profile')
        if not all(x.get('complete') and x.get('natural',regime=='W') and x.get('identity') and x.get('resources') and x.get('deadline') and x.get('samples') for x in (a,b)):return {'status':'FAIL_OR_INCOMPLETE_EVIDENCE'}
        if regime=='W' and (a['input_sha256'],a['schedule_sha256'])!=(b['input_sha256'],b['schedule_sha256']):raise GateError('fixed inputs/call plan changed')
        if regime=='S':
            if not all(x['functional'] for x in (a,b)):return {'status':'NO_GO_FUNCTIONAL'}
            if not all(x['nominal153'] and x['prefix'] for x in (a,b)):divergent=True
        for k in metrics:gains[k].append(paired(a[k],b[k]))
    med={k:median(v) for k,v in gains.items()}
    if divergent:return {'status':'INCONCLUSIVE_NOMINAL153','gains':gains,'medians':med}
    primary=metrics[0];threshold=5 if regime=='W' else 15
    good=med[primary]>=threshold and all(g>0 for g in gains[primary])
    if regime=='W':good &= all(med[k]>=-5 for k in metrics[1:])
    else:
        good &= med['SQL_validated_s'] >= (8 if confirmation else 0)
        if confirmation:good &= all(g>0 for g in gains['SQL_validated_s'])
        good &= all(med[k]>=-5 for k in metrics[2:])
    return {'status':('GO' if good else 'NO_GO')+'_'+regime+('_CONFIRMATION' if confirmation else '_SCREEN'),'gains':gains,'medians':med,'scope':'fixed input work' if regime=='W' else 'natural utility; messages/reasoning counts may differ, no equal-compute claim'}
