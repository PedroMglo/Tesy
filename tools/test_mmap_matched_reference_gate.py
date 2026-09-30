import unittest,copy,json,tempfile
from pathlib import Path
from mmap_matched_reference_gate import gate
from mmap_phase_gate import PHASES
ROOT=Path(__file__).resolve().parents[1]
MAP=ROOT/'results/c172-native-ffn-plan-model-free-20260930T1458Z/reference-map.tsv'
class Matched(unittest.TestCase):
 def test_numeric_and_plan_negatives(self):
  x={'schema':'c149-upstream-cpu-expert-layer-reference-v1','layer':24,'device':'cpu','canonical_layer_bytes':1697956352,'all_bitwise':True,'numeric_rows':5,'masked_rows':0,'router_backend':'CPU','expert_backend':'CPU','reduction_backend':'CUDA0','plan_assertions':True,'rows':[]}
  for phase in PHASES:
   r={'phase':phase,'state':'NUMERIC','tokens':32 if phase=='prefill0' else 1,'routing_ids_equal':True,'routing_weights_bitwise':True,'ffn_bitwise':True};r.update({k:0 for k in ('routing_weights_max_abs','routing_weights_rmse','routing_weights_nonfinite','ffn_max_abs','ffn_rmse','ffn_nonfinite')});x['rows'].append(r)
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'output';p.write_text(json.dumps(x));gate(p,24,MAP)
   for field,bad in [('router_backend','CUDA0'),('expert_backend','CUDA0'),('reduction_backend','CPU'),('plan_assertions',False)]:
    y=copy.deepcopy(x);y[field]=bad;p.write_text(json.dumps(y))
    with self.subTest(field=field),self.assertRaises(ValueError):gate(p,24,MAP)
   for mutate in ('missing','nonfinite','mismatch','truncated'):
    y=copy.deepcopy(x)
    if mutate=='missing':y['rows'].pop()
    elif mutate=='nonfinite':y['rows'][0]['ffn_nonfinite']=1
    elif mutate=='mismatch':y['rows'][0]['ffn_bitwise']=False
    p.write_text(json.dumps(y) if mutate!='truncated' else '{')
    with self.subTest(mutation=mutate),self.assertRaises(ValueError):gate(p,24,MAP)
if __name__=='__main__':unittest.main()
