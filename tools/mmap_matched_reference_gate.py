"""Prospective matched-plan reference gate; historical C169 remains untouched."""
import csv,json,sys
from pathlib import Path
from mmap_phase_gate import reference_result

def gate(path,layer,plan_map):
 x=reference_result(path,layer)
 rows=list(csv.DictReader(Path(plan_map).open(),delimiter='\t'))
 if len(rows)!=36 or [int(r['layer']) for r in rows]!=list(range(36)):raise ValueError('map cardinality/order')
 r=rows[layer]
 if x.get('router_backend')!=r['router'] or x.get('expert_backend')!=r['experts'] or x.get('reduction_backend')!=r['reduction'] or x.get('plan_assertions') is not True:raise ValueError('actual reference plan mismatch')
 return x
if __name__=='__main__':print(json.dumps(gate(Path(sys.argv[1]),int(sys.argv[2]),Path(sys.argv[3]))))
