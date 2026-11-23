import json,tempfile,unittest
from pathlib import Path
import numpy as np
from expert_prediction_corpus_gate import inspect

class Corpus(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.fixture={'ids':[1]*1800}
  self.v=dict(schema='task-separated-original-R0-score-corpus-v1',model_original=True,case='known',decode_calls=2,input_ids=self.fixture['ids'],profile='R0',mode=0,source_horizon=2,CPU_layers=[2,24],CPU_backend_threads=8,byte_forecasting=False,trained_weights=False,reference_supplied=False,capture_cap=128,template_date='2026-09-30',reasoning_effort='medium',sampling_policy='native-greedy-temp0-seed42',feature_rows=46,true_label_rows=46,prefix_s=1.,capture_decode_s=1.,original_native_feature_cost_us=1.,consumed_native_ids=[2,2],native_argmax_ids=[2,2,2],terminal_eog=False)
  scores=np.tile(np.arange(128,dtype='<f4'),(2,23,1));scores.tofile(self.root/'early-native-scores.f32');scores.tofile(self.root/'true-routing-scores.f32')
  (self.root/'actual-router-ids.json').write_text(json.dumps([124,125,126,127]*46));rows=np.zeros((3,201088),dtype='<f4');rows[:,2]=1.;rows.tofile(self.root/'first33.logits.f32');self.save()
 def tearDown(self):self.temp.cleanup()
 def save(self):(self.root/'result.json').write_text(json.dumps(self.v))
 def test_known_rank_and_greedy_rows(self):self.assertEqual(inspect(self.root,self.fixture,'known')['decode_calls'],2)
 def test_missing_position_or_capture(self):
  for key,value in [('native_argmax_ids',[2]),('feature_rows',0),('capture_cap',32),('byte_forecasting',True)]:
   old=self.v.copy();self.v[key]=value;self.save()
   with self.assertRaises(ValueError):inspect(self.root,self.fixture,'known')
   self.v=old
 def test_false_true_router_rejected(self):
  (self.root/'actual-router-ids.json').write_text(json.dumps([0,1,2,3]*46))
  with self.assertRaises(ValueError):inspect(self.root,self.fixture,'known')
 def test_nonfinite_or_truncated_label(self):
  p=self.root/'true-routing-scores.f32';x=np.fromfile(p,dtype='<f4');x[0]=float('nan');x.tofile(p)
  with self.assertRaises(ValueError):inspect(self.root,self.fixture,'known')
  p.write_bytes(b'\0'*4)
  with self.assertRaises(ValueError):inspect(self.root,self.fixture,'known')
 def test_no_native_fake_continuation(self):
  self.v['consumed_native_ids']=[2,3];self.save()
  with self.assertRaises(ValueError):inspect(self.root,self.fixture,'known')
 def test_clock_not_missing_nan_or_zero(self):
  for val in [None,float('nan'),0.]:
   self.v['capture_decode_s']=val;self.save()
   with self.assertRaises(ValueError):inspect(self.root,self.fixture,'known')
if __name__=='__main__':unittest.main()
