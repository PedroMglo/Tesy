"""Prospective private R0 transport bridge; historical gates unchanged."""
import argparse,json
from pathlib import Path
from c210_witness_gate import qualified
from c70_full_boundary_gate import _index
from c7_boundary_gate import CORE,sha

def compare(root,reference):
    root,reference=Path(root),Path(reference)
    old,new=qualified(reference),qualified(root)
    for key in ('core','masks','logits'):
        if old[key]!=new[key]:raise ValueError('same-profile transport payload differs: '+key)
    def metadata(path):
        return {(r['phase'],r['layer'],r['name']):{k:r[k] for k in ('chunk','first_abs','state_tokens','type','ne','nb','bytes')} for r in _index(path) if r['name'] in CORE}
    if metadata(root)!=metadata(reference):raise ValueError('state/shape/stride metadata differs')
    for name in ('masked.tsv','phases.txt','stages.txt'):
        if (root/name).read_bytes()!=(reference/name).read_bytes():raise ValueError('masked/phase/stage contract differs')
    return {'status':'PASS_SELECTED_R0_EXPERT_STORE_NUMERICAL_BRIDGE','core_payloads':len(new['core']),'numeric_states':new['coverage']['numeric_states'],'masked_states':new['coverage']['masked_states'],'full_logits':len(new['logits']),'prospective_witness':new['prospective_witness'],'reference':str(reference),'reference_index_sha256':sha(reference/'index.tsv'),'scope':'Selected 189+32 original R0: bytes, router/FFN core, masks, state metadata and finite complete logits; no universal8K/latency claim'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=compare(a.root,a.reference)
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(out['status'])
