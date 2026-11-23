import unittest
from expert_native_stage_scenario import NativeStageService

class NativeQueue(unittest.TestCase):
    def jobs(self):return {k:{'read':100.,'copy':2.,'order':i} for i,k in enumerate('abcdefghijkl')}
    def test_consumer_occupies_worker_until_producer(self):
        s=NativeStageService(self.jobs(),1.,128*2**20)
        for k in 'abc':s.request(k,False)
        s.request('a',True);s.request('d',True)
        self.assertIn('a',s.blocked);self.assertEqual(s.jobs['d']['primary'],'QUEUED')
        s.wait(['a','d']);self.assertEqual(s.blocked_worker_us,100.);self.assertEqual(s.now,202.)
    def test_ready_copy_and_finish_expiration(self):
        s=NativeStageService(self.jobs(),1.,128*2**20);s.request('a',False);s.advance(100);s.request('a',True);s.wait(['a'])
        self.assertEqual(s.now,102.);self.assertEqual(s.reads,1);self.assertEqual(s.occupied,0)
        s.request('b',False);s.cancel('b');self.assertEqual(s.occupied,1);s.finish();self.assertEqual(s.occupied,0)
    def test_queued_fallback_capacity_and_no_free_loading(self):
        s=NativeStageService(self.jobs(),1.,128*2**20)
        for k in 'abcdefghijk':s.request(k,False)
        self.assertEqual(s.no_capacity,1);self.assertEqual(s.occupied,10)
        s.request('d',True);self.assertEqual(s.jobs['d']['stage'],'NONE');self.assertEqual(s.jobs['d']['primary'],'RUN_FULL')
        s.wait(['d']);s.finish();self.assertEqual(s.occupied,0)
if __name__=='__main__':unittest.main()
