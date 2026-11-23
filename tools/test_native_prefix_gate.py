from copy import deepcopy
import json,tempfile,unittest
from pathlib import Path
from native_prefix_gate import gate
class PrefixGate(unittest.TestCase):
 def test_valid_and_negative_controls(self):
  ids=list(range(73));row={'id':'fixture','usage':{'completion_tokens':10,'prompt_tokens':73},'finish_reason':'stop','message':{'content':'AB'},'timings':{'cache_n':0,'prompt_n':73}};other=deepcopy(row);other['id']='again';other['timings']={'cache_n':72,'prompt_n':1};raw={'results':[row,other],'stop_reasons':[],'returncode':0}
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'run.json';i=Path(t)/'ids.json';i.write_text(json.dumps({'ids':ids}));p.with_name('run.tokenization.json').write_text(json.dumps({'first':ids,'second':ids}))
   p.write_text(json.dumps(raw));self.assertEqual(gate(p,i)['cache_n'],[0,72])
   for mutate in (lambda x:x['results'][1]['timings'].update(cache_n=0,prompt_n=73),lambda x:x['results'][1]['timings'].update(prompt_n=2),lambda x:x['results'][0].update(finish_reason='length'),lambda x:x['results'][0]['message'].update(content='wrong'),lambda x:x.update(stop_reasons=['OOM']),lambda x:x.update(results=x['results'][:1])):
    x=deepcopy(raw);mutate(x);p.write_text(json.dumps(x))
    with self.assertRaises((ValueError,RuntimeError)):gate(p,i)
   p.write_text(json.dumps(raw));p.with_name('run.tokenization.json').write_text(json.dumps({'first':ids,'second':ids+[1]}))
   with self.assertRaises(ValueError):gate(p,i)
if __name__=='__main__':unittest.main()
