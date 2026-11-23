"""Focused boundary tests, no weights/forward or performance evidence."""
import copy,json,math,unittest
from pathlib import Path
from expert_store_cost_gate import transport,evaluate
from r2_causal_gate import validate
class Gate(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  root=Path(__file__).resolve().parents[1];p=json.loads((root/'results/c280-r2-three-way-causal-cost-20261005/protocol.json').read_text());cls.data={}
  for r in p['runs']:
   cmd=r['command']
   if cmd[5]=='R0':cls.data[cmd[3]]=(json.loads((root/Path(cmd[4])).joinpath('result.json').read_text()) if not Path(cmd[4]).is_absolute() else json.loads((Path(cmd[4])/'result.json').read_text()),json.loads(Path(cmd[2]).read_text())[cmd[3]])
 def cases(self,speed=.8):
  cases={}
  for c,(original,fixture) in self.data.items():
   rows=[]
   for t in ['ORIGINAL','EXPERT_CONTIGUOUS','EXPERT_CONTIGUOUS','ORIGINAL']:
    v=copy.deepcopy(original);v.update(transport=t,store_loads_complete=0 if t=='ORIGINAL' else 1,store_logical_weight_bytes=0 if t=='ORIGINAL' else 13219200,store_manifest_env=None if t=='ORIGINAL' else '/frozen/manifest')
    if t!='ORIGINAL':
     for k in ['prefix_s','prefill153_s','decode32_s','total_s']:v[k]*=speed
    validate(v,fixture,'R0',c);transport(v,t);rows.append(v)
   cases[c]=rows
  return cases
 def test_known_positive_negative(self):
  self.assertEqual(evaluate(self.cases())['status'],'GO_INTEGRATED_EXPERT_SERVICE_COST');self.assertEqual(evaluate(self.cases(1.1))['status'],'NO_GO_INTEGRATED_EXPERT_SERVICE_COST')
 def test_empty_cardinality(self):
  with self.assertRaises(ValueError):evaluate({})
  c=self.cases();c['nominal153']=[]
  with self.assertRaises(ValueError):evaluate(c)
 def test_transport_missing_load(self):
  v=self.cases()['nominal153'][1];v['store_loads_complete']=0
  with self.assertRaises(ValueError):transport(v,'EXPERT_CONTIGUOUS')
 def test_nonfinite_and_missing_ids(self):
  c='nominal153';v,fixture=self.data[c]
  for key,value in [('prefill153_s',float('nan')),('decode32_s',float('inf')),('official_input_ids',[]),('output_rows',0)]:
   bad=copy.deepcopy(v);bad[key]=value
   with self.assertRaises(ValueError):validate(bad,fixture,'R0',c)
 def test_state_mismatch(self):
  c=self.cases();c['code153'][1]['initial']['n_calls']+=1
  with self.assertRaises(ValueError):evaluate(c)
if __name__=='__main__':unittest.main()
