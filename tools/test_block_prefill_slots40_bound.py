import unittest
from block_prefill_slots40_bound import layer_bound


class BoundTests(unittest.TestCase):
    def test_seen_ready_is_not_initial_residency_and_overlap_is_not_worker_sum(self):
        def event(kind, expert=7, state=2, slot=0, generation=1, time=0):
            return dict(kind=kind,expert=expert,state=state,slot=slot,generation=generation,
                        mono_us=time,call_id=1,wave=0,n_tokens=32)
        rows=[event('DEMAND'),event('LOAD_BEGIN'),event('WAIT_BEGIN',time=1),
              event('LOAD_END',time=3),event('WAIT_END',time=4)]
        r=layer_bound(rows,{'bytes':13})
        self.assertEqual(r['repeated_after_observed_ready_or_load'],1)
        self.assertEqual(r['duplicate_eligible_waits'],[(1,4)])
        self.assertTrue(r['initial_ready'].startswith('UNKNOWN'))
        rows[0]['state']=1  # In-flight does not certify a ready copy.
        r=layer_bound(rows,{'bytes':13})
        self.assertEqual(r['repeated_after_observed_ready_or_load'],0)
        self.assertEqual(r['duplicate_eligible_waits'],[])

    def test_capacity_credit_bounded_and_empty_rejected(self):
        rows=[dict(kind='DEMAND',expert=e,state=0,call_id=1,wave=0,n_tokens=32) for e in range(50)]
        r=layer_bound(rows,{'bytes':13})
        self.assertEqual(r['optimistic_minimum_logical_bytes'],130)
        with self.assertRaises(ValueError):layer_bound([],{'bytes':13})

if __name__=='__main__':unittest.main()
