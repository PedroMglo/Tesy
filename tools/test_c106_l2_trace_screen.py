import unittest

from c106_l2_trace_screen import simulate, union_us


def row(kind, expert, state=0, tokens=1):
    return {'kind':kind,'layer':0,'expert':expert,'state':state,'n_tokens':tokens}


class FixedTraceL2(unittest.TestCase):
    def test_capacity_changes_saved_absent_demand(self):
        events=[row('LOAD_END',1),row('LOAD_END',2),row('DEMAND',1)]
        self.assertEqual(simulate(events,1,'on_load_lru')[('decode','CPU')]['saved'],0)
        self.assertEqual(simulate(events,2,'on_load_lru')[('decode','CPU')]['saved'],1)

    def test_primary_hit_and_inflight_are_not_nvme_demand(self):
        events=[row('LOAD_END',1),row('DEMAND',1,state=1),row('DEMAND',1,state=2)]
        summary=simulate(events,1,'on_load_lru')[('decode','CPU')]
        self.assertEqual((summary['misses'],summary['saved'],summary['hits_primary'],
                          summary['inflight_primary']),(0,0,1,1))

    def test_eviction_only_requires_an_eviction(self):
        events=[row('LOAD_END',7),row('DEMAND',7),row('EVICT',7),row('DEMAND',7)]
        self.assertEqual(simulate(events,1,'on_evict_lru')[('decode','CPU')]['saved'],1)

    def test_overlapping_waits_use_union_not_sum(self):
        self.assertEqual(union_us([(0,10),(5,20),(30,35)]),25)


if __name__=='__main__':unittest.main()
