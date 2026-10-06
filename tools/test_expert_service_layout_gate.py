import copy,json,tempfile,unittest
from pathlib import Path
from expert_service_layout_gate import inspect,evaluate,SLAB
class Gate(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'result.json'
  self.good={'status':'PASS_LOSSLESS_SAMPLE_SERVICE','arm':'A','component_checks':384,'source_fd_direct':True,'pack_fd_direct':True,'memory_alignment':4096,'offset_alignment':4096,'reports':[{'tier':tier,'experts_served':256,'logical_weight_bytes':256*3*SLAB,'aligned_request_bytes':256*3*SLAB+4096,'pread_calls':768,'destination_verified':True,'destination_shape':[2880,2880],'service_s':1.5} for tier in ['CPU','GPU']]}
 def tearDown(self):self.tmp.cleanup()
 def check(self,v):self.path.write_text(json.dumps(v));return inspect(self.path,'A')
 def test_positive(self):self.check(self.good)
 def test_missing_tiers(self):
  for rs in [[],self.good['reports'][:1],self.good['reports']*2]:
   x=copy.deepcopy(self.good);x['reports']=rs
   with self.assertRaises(ValueError):self.check(x)
 def test_invalid_measurement(self):
  for key,value in [('component_checks',383),('source_fd_direct',False),('arm','B')]:
   x=copy.deepcopy(self.good);x[key]=value
   with self.assertRaises(ValueError):self.check(x)
 def test_work_or_nan_or_zero(self):
  for key,value in [('service_s',float('nan')),('service_s',float('inf')),('service_s',0),('experts_served',255),('pread_calls',256),('destination_verified',False)]:
   x=copy.deepcopy(self.good);x['reports'][0][key]=value
   with self.assertRaises(ValueError):self.check(x)
 def test_family_cardinality_and_projection(self):
  directory=Path(self.tmp.name);runs=[]
  for i,arm in enumerate(['A','B','B','A']):
   value=copy.deepcopy(self.good);value['arm']=arm
   for report in value['reports']:
    report['pread_calls']=768 if arm=='A' else 256;report['service_s']=1.5 if arm=='A' else 1
   path=directory/f'arm{i}.json';path.write_text(json.dumps(value));runs.append({'id':f'fixed{i}','arm':arm,'result_path':str(path)})
  protocol={'runs':runs,'projection':{'C280_R0_cases':{case:{'CPU_generations':100,'GPU_generations':50,'optimistic_normal_wait_decode_fraction':.8} for case in ['nominal153','code153']},'integration_engineering_h':8}}
  path=directory/'protocol.json';path.write_text(json.dumps(protocol));self.assertEqual(evaluate(directory)['status'],'GO_LAYOUT_INTEGRATION_INVESTMENT')
  for change in [[],runs[:2],runs+[runs[0]],runs[:3]+[runs[0]]]:
   broken=copy.deepcopy(protocol);broken['runs']=change;path.write_text(json.dumps(broken))
   with self.assertRaises(ValueError):evaluate(directory)
  for cases in [{},{'nominal153':protocol['projection']['C280_R0_cases']['nominal153']}]:
   broken=copy.deepcopy(protocol);broken['projection']['C280_R0_cases']=cases;path.write_text(json.dumps(broken))
   with self.assertRaises(ValueError):evaluate(directory)
if __name__=='__main__':unittest.main()
