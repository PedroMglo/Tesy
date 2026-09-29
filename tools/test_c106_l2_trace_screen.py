import unittest

from c2_gate import GateError
from c106_l2_trace_screen import simulate, union_us, c105_phase_boundary


def row(kind, expert, state=0, tokens=1):
    return {'kind':kind,'layer':0,'expert':expert,'state':state,'n_tokens':tokens}


def simulate_test(events, slots, mode):
    return simulate(events, slots, mode, destinations={0:'CPU'},
                    phase_of=lambda _row:'decode')


class FixedTraceL2(unittest.TestCase):
    def test_capacity_changes_saved_absent_demand(self):
        events=[row('LOAD_END',1),row('LOAD_END',2),row('DEMAND',1)]
        self.assertEqual(simulate_test(events,1,'on_load_lru')[('decode','CPU')]['saved'],0)
        self.assertEqual(simulate_test(events,2,'on_load_lru')[('decode','CPU')]['saved'],1)

    def test_primary_hit_and_inflight_are_not_nvme_demand(self):
        events=[row('LOAD_END',1),row('DEMAND',1,state=1),row('DEMAND',1,state=2)]
        summary=simulate_test(events,1,'on_load_lru')[('decode','CPU')]
        self.assertEqual((summary['misses'],summary['saved'],summary['hits_primary'],
                          summary['inflight_primary']),(0,0,1,1))
        self.assertEqual(summary['inflight_primary'],1)
        self.assertEqual(summary['hits_primary'],1)

    def test_eviction_only_requires_an_eviction(self):
        events=[row('LOAD_END',7),row('DEMAND',7),row('EVICT',7),row('DEMAND',7)]
        self.assertEqual(simulate_test(events,1,'on_evict_lru')[('decode','CPU')]['saved'],1)

    def test_overlapping_waits_use_union_not_sum(self):
        self.assertEqual(union_us([(0,10),(5,20),(30,35)]),25)

    def test_c105_final_prefill_is_not_decode(self):
        singles=[{'kind':'DEMAND','n_tokens':1,'layer':35,'seq':i} for i in range(4)]
        singles += [{'kind':'DEMAND','n_tokens':1,'layer':layer,'seq':i+4}
                    for i,layer in enumerate(layer for _token in range(32)
                                             for layer in range(36) for _expert in range(4))]
        self.assertEqual(c105_phase_boundary(singles),4)
        missing=singles[:4]+singles[5:]
        with self.assertRaises(GateError):c105_phase_boundary(missing)
        reordered=singles.copy();reordered[4],reordered[8]=reordered[8],reordered[4]
        with self.assertRaises(GateError):c105_phase_boundary(reordered)

    def test_other_placement_uses_metadata(self):
        event=[row('DEMAND',7)]
        result=simulate(event,1,'on_load_lru',destinations={0:'GPU'},
                        phase_of=lambda _row:'prefill')
        self.assertEqual(result[('prefill','GPU')]['misses'],1)


if __name__=='__main__':unittest.main()
