"""New authoritative load-order fidelity boundary, historical R2 gates intact."""
import argparse
import json
from pathlib import Path
from block_layer_reuse_gate import inspect,STAGES


def compare(current,reference):
    expected={f'{layer}:{stage}' for layer in range(36) for stage in STAGES}
    expected.update(['prefill.logits.f32',*[f'decode{i}.logits.f32' for i in range(6)]])
    for v in (current,reference):
        if v.get('status')!='PASS_NATIVE_R2_COMPLETE_LAYER_CAPTURE' or set(v.get('stage_payloads',{}))!=expected:
            raise ValueError('complete inspected216stage/seven logit contract required')
        if len(v.get('native_argmax_ids',[]))!=7 or any(type(x)is not int or not 0<=x<201088 for x in v['native_argmax_ids']):
            raise ValueError('native output accounting incomplete')
    if current['stage_payloads']!=reference['stage_payloads']:
        raise ValueError('authoritative load order changed numerical payloads/logits')
    for key in ('layers','pending_queue','n_calls'):
        if current['initial'][key]!=reference['initial'][key]:
            raise ValueError('ordered same-profile initial state differs')
    if current['native_argmax_ids']!=reference['native_argmax_ids']:
        raise ValueError('ordered native argmax trajectory differs')
    return dict(status='PASS_SELECTED_AUTHORITATIVE_LAST_USE_FIDELITY',
                full_layer_stages=216,full_logits=7,
                consumer_components=current['consumer_components'],
                scope='R2 whole153 plus6 teacher-forced calls, unchanged native arithmetic under new load order; not timing/universal fidelity')


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    f=json.loads(a.fixture.read_text())['anchor-nominal153']
    result=compare(inspect(a.directory,f,'r2-reuse'),inspect(a.reference,f,'r2-reuse'))
    with a.output.open('x') as out:json.dump(result,out,indent=2,allow_nan=False);out.write('\n')
    print(result['status'])

if __name__=='__main__':main()
