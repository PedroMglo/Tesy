import copy, json, tempfile, unittest
from pathlib import Path
import numpy as np

import expert_prediction_holdout_gate as gate

class Prefix(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.fixture={'ids':[42]*2000}
 def tearDown(self):self.temp.cleanup()
 def make(self,name,n=16,on=False):
  r=self.root/name;r.mkdir();ids=list(range(10,10+n));argmax=ids+[99]
  state={'pending_queue':0,'n_calls':123,'layers':[{'layer':l,'slot_expert':list(range(40)),'slot_state':[2]*40,'slot_generation':[1]*40,'slot_claimed':[False]*40} for l in range(36)]}
  plan=[min(256,1847-p) for p in range(0,1847,256)]+[153]
  v={'status':'COMPLETE_NATIVE_PREDICTION_HELDOUT_PREFIX','profile':'R0','case':'synthetic','official_input_ids':self.fixture['ids'],'teacher_forced_ids':ids,'native_argmax_ids':argmax,'native_output_ids':ids+([99] if n<32 else []),'terminal_eog':n<32,'external_prefill_calls':plan,'decode_calls':n,'decode_positions':[2000,1999+n] if n else None,'output_rows':n+1,'vocab':201088,'FFN_last_layer_rows_per_call':1,'mode':0,'layerspan':32,'numerical_FFN_tiles':[32,32,32,32,25],'last_use_order_env':None,'initial_prefix_mode':0,'full_row_retention_bytes':(n+1)*201088*4,'heldout':True,'training':False,'sampling_policy':'native-greedy-temp0-seed42','template_date':'2026-09-30','reasoning_effort':'medium','prefix_capture_cap':32,'trace':True,'trace_capacity':131072,'continuation_origin':'PROVIDED_NATIVE_CONTROL_PREFIX' if on else 'NATIVE_GREEDY_CONTROL_PREFIX','prefix_s':2.,'prefill153_s':1.,'decode_window_s':float(n) if n else .000001,'total_s':1.+(float(n) if n else .000001),'initial':state,'final':copy.deepcopy(state),'transport':'ORIGINAL','store_loads_complete':0,'store_logical_weight_bytes':0,'store_manifest_env':None,'trace_bytes_reserved':8*2**20}
  logits=np.zeros((n+1,201088),dtype='<f4');logits[np.arange(n+1),argmax]=10;logits.tofile(r/'all-position.logits.f32')
  rows=[]
  def add(k,t,c,l=-1,e=-1,b=0):rows.append(dict(zip(gate.FIELDS,(k,t,c,1,l,e,e if e>=0 else -1,1 if e>=0 else 0,-1,b,1))))
  for c in range(n+1):
   t=10000+c*10000;add(15,t,c)
   if c:
    for l in range(36):
     if l<25:add(1,t+l*100+1,c,l)
     add(2,t+l*100+2,c,l)
     for e in range(4):add(3,t+l*100+3,c,l,e,2)
     add(14,t+l*100+4,c,l)
   add(16,t+9000,c)
  v['trace_events']=len(rows);(r/'events.tsv').write_text(' '.join(gate.FIELDS)+'\n'+''.join(' '.join(str(x[k]) for k in gate.FIELDS)+'\n' for x in rows))
  scores=np.zeros((n,23,128),dtype='<f4');scores[:,:,:4]=np.array([4,3,2,1]);scores.tofile(r/'true-routing-scores.f32')
  records=[{'call':c,'source_layer':l,'target_layer':l+2,'prediction_ids':[0,1,2,3],'available_primary_state':[{'expert':e,'slot':e,'state':2,'generation':1} for e in range(4)],'complete_predictor_us':5} for c in range(1,n+1) for l in range(23)] if on else []
  meta={'enabled':on,'training':False,'decode_calls':n,'schema':'original-destination-gate-on-earlier-residual-v1','source_horizon':2,'CPU_backend_threads':8,'capture_bytes':10*2**20,'records':records};(r/'estimator.json').write_text(json.dumps(meta))
  if on:np.zeros((n,23,2880),dtype='<f4').tofile(r/'earlier-input.f32');scores.tofile(r/'prediction-scores.f32')
  (r/'result.json').write_text(json.dumps(v));return r
 def check(self,r,on=False,control=None):return gate.prefix_arm(r,self.fixture,'synthetic',on,control)
 def mutate(self,r,key,value):v=json.loads((r/'result.json').read_text());v[key]=value;(r/'result.json').write_text(json.dumps(v))
 def test_complete_actual_counts_and_pair(self):
  a=self.make('a');b=self.make('b',on=True);self.assertTrue(self.check(a)['investment_window_valid']);self.assertTrue(self.check(b,True,a)['investment_window_valid'])
  jobs,groups,tail,observed,initial,late,t0=gate.extract_prefix(gate.prefix_events(a/'events.tsv',True,16),16);self.assertEqual(len(groups),16*36)
 def test_eos_partial_zero_and_cap_bonus(self):
  for n in (0,1,15,32):
   a=self.make(str(n),n);v=self.check(a);self.assertEqual(v['investment_window_valid'],n>=16)
   if n<16:self.assertEqual(v['status'],'VALID_PARTIAL_EOS_PREFIX_NOT_COMPUTABLE_FOR_INVESTMENT')
  with self.assertRaises(ValueError):gate.extract_prefix([],0)
 def test_cardinality_inputs_sampler_and_counts(self):
  r=self.make('a');original=(r/'result.json').read_text()
  for k,v in [('official_input_ids',[]),('decode_calls',False),('teacher_forced_ids',[]),('native_output_ids',[]),('decode_positions',[2001,2016]),('sampling_policy','random'),('output_rows',1),('terminal_eog',False)]:
   (r/'result.json').write_text(original);self.mutate(r,k,v)
   with self.assertRaises(ValueError):self.check(r)
 def test_full_logits_missing_nonfinite_and_cross_profile(self):
  a=self.make('a');b=self.make('b',on=True);p=b/'all-position.logits.f32';old=p.read_bytes();p.write_bytes(old[:-4])
  with self.assertRaises(ValueError):self.check(b,True,a)
  p.write_bytes(old);arr=np.memmap(p,dtype='<f4',mode='r+');arr[0]=np.nan;arr.flush();del arr
  with self.assertRaises(ValueError):self.check(b,True,a)
  p.write_bytes(old);arr=np.memmap(p,dtype='<f4',mode='r+');arr[0]=.5;arr.flush();del arr
  with self.assertRaises(ValueError):self.check(b,True,a)
 def test_observer_missing_feature_duplicate_and_future(self):
  r=self.make('a');s=(r/'events.tsv').read_text();lines=s.splitlines();i=next(i for i,x in enumerate(lines) if x.startswith('1 '))
  for ls in (lines[:i]+lines[i+1:],lines+[lines[i]],lines[:i]+[lines[i].replace(lines[i].split()[1],'999999999',1)]+lines[i+1:]):
   (r/'events.tsv').write_text('\n'.join(ls)+'\n')
   with self.assertRaises(ValueError):self.check(r)
 def test_forecast_exact_labels_states_cost(self):
  a=self.make('a');b=self.make('b',on=True);p=b/'estimator.json';old=p.read_text()
  for change in ('omit','cost','state','ids'):
   m=json.loads(old)
   if change=='omit':m['records'].pop()
   elif change=='cost':m['records'][0]['complete_predictor_us']=float('nan')
   elif change=='state':m['records'][0]['available_primary_state'][0]['generation']=0
   else:m['records'][0]['prediction_ids']=[0,0,2,3]
   p.write_text(json.dumps(m))
   with self.assertRaises(ValueError):self.check(b,True,a)
 def test_initial_state_and_true_label_corruption(self):
  a=self.make('a');b=self.make('b',on=True);v=json.loads((b/'result.json').read_text());v['initial']['n_calls']+=1;(b/'result.json').write_text(json.dumps(v))
  with self.assertRaises(ValueError):self.check(b,True,a)
  r=a/'true-routing-scores.f32';arr=np.memmap(r,dtype='<f4',mode='r+');arr[9]=100;arr.flush();del arr
  with self.assertRaises(ValueError):self.check(a)
 def test_prefix_progress_identity(self):
  a=self.make('a');p=a/'prefix-progress.json';v={'phase':'PREFIX_PREPARATION','completed_positions':1847,'required_prefix_positions':1847,'pending_call_size':0,'n_calls':123,'logical_miss_generations':1};p.write_text(json.dumps(v))
  self.assertTrue(gate.prefix_arm(a,self.fixture,'synthetic',False,require_prefix_progress=True)['measurement_valid'])
  for key,value in [('completed_positions',1792),('pending_call_size',256),('n_calls',0),('logical_miss_generations',False)]:
   m=dict(v);m[key]=value;p.write_text(json.dumps(m))
   with self.assertRaises(ValueError):gate.prefix_arm(a,self.fixture,'synthetic',False,require_prefix_progress=True)
if __name__=='__main__':unittest.main()
