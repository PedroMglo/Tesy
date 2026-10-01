import unittest
from readiness_feasibility import optimistic_overlap, ordered_gain, measured_envelope

class ReadinessEnvelope(unittest.TestCase):
    def test_all_missing_no_work_before_commit(self):
        self.assertEqual(optimistic_overlap([10]*4,8,10,0),0)
        self.assertEqual(ordered_gain([10]*4,[3,2,1,0],8,0,12),2)
    def test_mixed_release_has_only_released_capacity(self):
        self.assertEqual(optimistic_overlap([0,0,10,10],8,10,0),4)
        self.assertEqual(ordered_gain([0,0,10,10],[0,1,2,3],8,0,10),4)
    def test_arrival_order_does_not_reorder_slots(self):
        self.assertEqual(ordered_gain([0,0,10,10],[2,3,0,1],8,0,10),0)
    def test_gains_do_not_sum_wait_and_load(self):
        case={'decode_s':1,'rows':[{'tier':'CPU','release_us':[0,0,10,10],
            'all_ready_us':10,'wait_begin_us':0,'wait_end_us':12,'slots':[0,1,2,3],
            'service_window_us':10,'wake_tail_us':2}]}
        result=measured_envelope(case,8,20)
        self.assertEqual(result['first_MMID']['optimistic_service_overlap_s'],4e-6)
        self.assertEqual(result['first_MMID']['separate_wake_tail_s'],2e-6)
    def test_invalid_release_and_cardinality_rejected(self):
        for releases,work,ready,start in [([],1,1,0),([3]*4,1,2,0),([1]*4,-1,1,0),([0]*4,1,0,1)]:
            with self.assertRaises(ValueError):optimistic_overlap(releases,work,ready,start)
        with self.assertRaises(ValueError):ordered_gain([0]*4,[0]*4,1,0,0)
    def test_all_hit_has_no_credit(self):
        self.assertEqual(optimistic_overlap([0]*4,8,0,0),0)
        self.assertEqual(ordered_gain([0]*4,[0,1,2,3],8,0,0),0)

if __name__=='__main__':unittest.main()
