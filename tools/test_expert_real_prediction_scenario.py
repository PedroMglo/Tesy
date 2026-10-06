import unittest
from expert_real_prediction_scenario import PredictedService
from expert_prediction_scenario import WEIGHT_BYTES
class RealQueue(unittest.TestCase):
 def service(self,arena=WEIGHT_BYTES):return PredictedService({i:{'read':10.,'copy':2.,'order':i} for i in range(8)},1.,arena)
 def test_wrong_queued_read_cancelled_before_dispatch(self):
  s=self.service();s.request(0,False);s.request(1,False);s.cancel(1);s.advance(10)
  self.assertEqual(s.jobs[1]['state'],'CANCELLED');self.assertEqual(s.reads,1)
 def test_wrong_running_nonpreemptible_until_completion(self):
  s=self.service();s.request(0,False);s.advance(2);s.cancel(0);self.assertEqual(s.staged,1);s.advance(10)
  self.assertEqual(s.staged,0);self.assertEqual(s.expired_reads,1)
 def test_wrong_ready_releases_bounded_arena(self):
  s=self.service();s.request(0,False);s.advance(10);s.request(1,False);s.cancel(0)
  self.assertEqual(s.jobs[1]['state'],'RUN_READ');self.assertEqual(s.peak,1)
 def test_demand_immune_to_expiry_and_complete_copy(self):
  s=self.service();s.request(0,False);s.advance(5);s.request(0,True);s.cancel(0);s.wait([0]);self.assertEqual(s.now,12)
 def test_false_running_delays_priority_demand_without_preemption(self):
  s=self.service(4*WEIGHT_BYTES)
  for i in range(4):s.request(i,False)
  s.advance(1);s.request(7,True);s.cancel(0);s.wait([7]);self.assertEqual(s.now,22);self.assertEqual(s.expired_reads,1)
if __name__=='__main__':unittest.main()
