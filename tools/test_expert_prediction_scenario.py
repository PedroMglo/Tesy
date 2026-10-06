import unittest
from expert_prediction_scenario import Service,WEIGHT_BYTES,gpu_prefill_gross_upper
class Scenario(unittest.TestCase):
 def service(self,n=8,arena=128*2**20):return Service({k:{'read':10.,'copy':2.,'order':k} for k in range(n)},1.,arena)
 def test_four_workers_and_complete_copy(self):
  s=self.service()
  for k in range(8):s.request(k,True)
  self.assertEqual(len(s.running),4);s.wait(list(range(8)));self.assertEqual(s.now,24.)
 def test_staging_not_published_until_true_demand(self):
  s=self.service();s.request(0,False);s.advance(10);self.assertEqual(s.jobs[0]['state'],'READY');self.assertEqual(s.staged,1)
  s.request(0,True);s.wait([0]);self.assertEqual(s.now,12);self.assertEqual(s.staged,0)
 def test_nonpreemptible_and_demand_priority(self):
  s=self.service()
  for k in range(5):s.request(k,False)
  s.advance(1);s.request(7,True);self.assertEqual(len(s.running),4)
  s.advance(10);self.assertTrue(any(k==7 for _,_,k,_ in s.running));self.assertEqual(s.jobs[4]['state'],'RUN_READ')
 def test_bounded_staging_includes_running_and_ready(self):
  s=self.service(arena=WEIGHT_BYTES)
  for k in range(8):s.request(k,False)
  self.assertEqual(len(s.running),1);s.advance(100);self.assertEqual(s.staged,1);self.assertEqual(s.jobs[1]['state'],'QUEUED')
  s.request(0,True);s.wait([0]);self.assertEqual(s.peak,1);self.assertTrue(len(s.running)<=4)
 def test_late_demand_retains_read(self):
  s=self.service();s.request(0,False);s.advance(5);s.request(0,True);s.wait([0]);self.assertEqual(s.now,12)
class GrossGPU(unittest.TestCase):
 def rows(self):
  r=[{'kind':15,'call':0,'us':1},{'kind':16,'call':0,'us':10001}]
  for i in range(5):
   r.extend([{'kind':1,'call':0,'layer':0,'us':i*2000+1}, {'kind':1,'call':0,'layer':24,'us':i*2000+1001}])
   r.extend([{'kind':11,'call':0,'layer':25,'route':i,'us':i*2000+1101},{'kind':12,'call':0,'layer':25,'route':i,'us':i*2000+1601}])
  return r
 def test_gross_contains_wait_subtraction_and_all_five_tiles(self):
  v=gpu_prefill_gross_upper(self.rows());self.assertEqual(v['gross_upper_us'],2500);self.assertEqual(v['remove_all_gross_percent'],25)
 def test_missing_feature_wait_endpoint(self):
  r=self.rows()
  for kind in (1,12):
   damaged=r.copy();damaged.pop(next(i for i,x in enumerate(damaged) if x['kind']==kind))
   with self.assertRaises(ValueError):gpu_prefill_gross_upper(damaged)
if __name__=='__main__':unittest.main()
