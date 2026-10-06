import unittest
from expert_prediction_scenario import Service,WEIGHT_BYTES
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
if __name__=='__main__':unittest.main()
