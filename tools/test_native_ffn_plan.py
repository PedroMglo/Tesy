import unittest,copy,json
from pathlib import Path
from native_ffn_plan import validate,compare_plan,compact,map_rows
P=Path(__file__).resolve().parents[1]/'results/c172-native-ffn-plan-model-free-20260930T1458Z/raw/native-plan.json'
class Plan(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.x=json.loads(P.read_text())
 def test_positive_native_plan(self):
  compare_plan(self.x,copy.deepcopy(self.x));self.assertEqual(len(compact(self.x)['plan_layers']),72)
  m=map_rows(self.x);self.assertEqual(m[23],(23,'CPU','CPU','CPU',0));self.assertEqual(m[24],(24,'CPU','CPU','CUDA0',1));self.assertEqual(m[25],(25,'CUDA0','CPU','CUDA0',1))
 def test_plan_counterexamples(self):
  mutations=['backend','provenance','move','copy','fusion','dtype','kernel','missing','cpu_as_gpu']
  for change in mutations:
   a=copy.deepcopy(self.x);ns=a['variants'][0]['nodes'];n=next(n for n in ns if n['name']=='ffn_moe_out-24')
   if change in ('backend','move'):n['backend']='CPU'
   if change=='provenance':n['output_buffer']='CPU'
   if change=='copy':n['inputs'].append(copy.deepcopy(n['inputs'][0]))
   if change=='fusion':n['optimizer_dependencies']=[]
   if change=='dtype':n['dtype']='f16'
   if change=='kernel':n['op']='MUL'
   if change=='missing':ns.remove(n)
   if change=='cpu_as_gpu':next(n for n in ns if n['name']=='ffn_moe_gate-23')['backend']='CUDA0'
   with self.subTest(change=change),self.assertRaises(ValueError):compare_plan(a,self.x)
 def test_strict_extra_field(self):
  a=copy.deepcopy(self.x);a['variants'][0]['nodes'][0]['silent']=1
  with self.assertRaises(ValueError):validate(a)
 def test_wrong_variant(self):
  a=copy.deepcopy(self.x);a['variants'][0]['tokens']=16
  with self.assertRaises(ValueError):validate(a)
if __name__=='__main__':unittest.main()
