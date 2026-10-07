"""One prospective diagnostic control/stage pair, not a performance screen."""
import argparse,json
from pathlib import Path
from r2_causal_gate import initial_identity

def main():
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();protocol=json.loads((a.directory/'protocol.json').read_text());runs=protocol['runs']
 if len(runs)!=3 or not runs[0].get('model_free') or [(x.get('case'),x.get('stage'),x.get('witness')) for x in runs[1:]]!=[('nominal153',False,False),('nominal153',True,True)] or len({x['id'] for x in runs})!=3:raise ValueError('exact canary orderedcardinality')
 vals=[json.loads((Path(x['command'][4])/'result.json').read_text()) for x in runs[1:]]
 if initial_identity(vals[0])!=initial_identity(vals[1]) or vals[0]['native_argmax_ids']!=vals[1]['native_argmax_ids']:raise ValueError('initial primary state or same-profile native output IDs differ')
 analyses=[json.loads((a.directory/(x['id']+'-analysis.json')).read_text()) for x in runs[1:]]
 if analyses[0]['full33_logits_sha256']!=analyses[1]['full33_logits_sha256'] or analyses[1]['consumed_with_complete_canonical_witness']!=8 or any(x['status']!='PASS_SELECTED_R0_CPU_STAGING_FIDELITY' for x in analyses):raise ValueError('native fullrow/canonical consumer evidence incomplete')
 out={'status':'PASS_SELECTED_REAL_STAGING_CANARY','arms':analyses,'scope':'Original R0 bitwise all33 selected rows with actual original-byte staging/nativeworker/authoritative routing+ownedcommit+canonicalconsumer checks. Diagnostic witness/capture included in metrics; no promotion latency estimate extracted. Next: observer-neutrality/trace-OFF integrated cost; no implicit candidate/preset/M4.'}
 with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
 print(out['status'])
if __name__=='__main__':main()
