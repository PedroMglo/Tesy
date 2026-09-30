"""Same-wave profile bridge and logger neutrality against qualified C140 states."""
import json,sys
from pathlib import Path
from c70_full_boundary_gate import inspect

def compare(a,b):
    x=inspect(a,skip_on=True);y=inspect(b,skip_on=True);bad=[]
    for field in ('core','logits','masks'):
        if x[field].keys()!=y[field].keys():raise ValueError('coverage keys changed: '+field)
        for key in x[field]:
            if x[field][key]!=y[field][key]:bad.append({'field':field,'key':str(key)})
    return {'status':'SAME_PROFILE_BITWISE_PASS' if not bad else 'FAIL_SAME_PROFILE','core_comparisons':len(x['core']),'full_logit_rows':len(x['logits']),'mismatch':bad,'coverage':x['coverage']}
if __name__=='__main__':
    reference,off,on,output=map(Path,sys.argv[1:]);result={'reference_bridge':compare(reference,off),'logger_neutrality':compare(off,on)}
    with output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result));raise SystemExit(0 if all(x['status']=='SAME_PROFILE_BITWISE_PASS' for x in result.values()) else 1)
