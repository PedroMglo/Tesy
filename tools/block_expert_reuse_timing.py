"""Complete isolated native layer service; not a full prefill speedup claim."""
import argparse
import json
import statistics
from pathlib import Path
from block_expert_reuse_gate import inspect
from block_verifier_contract import paired_gain

LAYERS=(0,12,24)
MODES=('timing-A','timing-B','timing-B','timing-A')


def evaluate(arms):
    if type(arms) is not list or len(arms)!=12:raise ValueError('twelve original attempted layer arms required')
    rows=[];out=[]
    for i,arm in enumerate(arms):
        layer=LAYERS[i//4];mode=MODES[i%4]
        rows.append(inspect(arm,layer,mode))
    for n,layer in enumerate(LAYERS):
        group=rows[4*n:4*n+4];pairs=[]
        for ia,ib in ((0,1),(3,2)):
            a,b=group[ia],group[ib]
            if arms[4*n+ia]['initial']!=arms[4*n+ib]['initial']:raise ValueError('paired initial empty pool/counters/capacity differ')
            pairs.append({'A_arm':ia+1,'B_arm':ib+1,'A_service_s':a['service_wall_s'],'B_service_s':b['service_wall_s'],
                'gain_percent':paired_gain(a['service_wall_s'],b['service_wall_s']),
                'A_actual_loads':a['actual_loads'],'B_actual_loads':b['actual_loads'],
                'logical_load_reduction':a['actual_loads']-b['actual_loads'],
                'A_logical_bytes':a['logical_loaded_bytes'],'B_logical_bytes':b['logical_loaded_bytes'],
                'A_wait_union_s':a['wait_union_s'],'B_wait_union_s':b['wait_union_s']})
        median=statistics.median(p['gain_percent'] for p in pairs)
        go=median>0 and all(p['gain_percent']>0 and p['logical_load_reduction']>0 for p in pairs)
        out.append({'layer':layer,'pairs':pairs,'median_service_gain_percent':median,
            'decision':'GO_SELECTED_LAYER_SHARED_LOAD_SERVICE' if go else 'NO_GO_SELECTED_LAYER_SHARED_LOAD_SERVICE'})
    return {'decision':'GO_SELECTED_OPERATOR_REUSE' if all(x['decision'].startswith('GO_') for x in out) else 'MIXED_OR_NO_GO_SELECTED_OPERATOR_REUSE',
            'layers':out,'scope':'Three disjoint captured CPU tiles; direct native load+compute+scatter+coordination. No full153/server timing, physical NVMe traffic or M4 claim. Later integration requires a workload-specific opportunity projection.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    protocol=json.loads((args.directory/'protocol.json').read_text());arms=[]
    if len(protocol['runs'])!=12 or len({x['id'] for x in protocol['runs']})!=12:raise ValueError('duplicate/omitted attempted arms')
    for i,run in enumerate(protocol['runs']):
        if (run['layer'],run['mode'])!=(LAYERS[i//4],MODES[i%4]):raise ValueError('frozen layer/paired order changed')
        path=args.directory/'raw'/(run['id']+'.operator.json');arms.append(json.loads(path.read_text()))
    result=evaluate(arms)
    with (args.directory/'timing-summary.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(result['decision'])

if __name__=='__main__':main()
