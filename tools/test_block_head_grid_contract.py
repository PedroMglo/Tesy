import unittest
from block_head_grid_contract import proposal_inputs,accept_grid

class GreedyHeadGrid(unittest.TestCase):
    def test_all_accept_and_every_rejection_respect_fixed_origin(self):
        for known in range(1,9):
            prefix=[101,102,103]+list(range(20,20+known))
            g,inp=proposal_inputs(prefix,origin=3,proposals=list(range(30,37)))
            self.assertEqual(g.start,3);self.assertEqual(len(inp),8)
            winners=list(inp[1:])+[50]
            for mismatch in range(known-1,8):
                changed=winners.copy();changed[mismatch]=99
                result=accept_grid(known,inp,changed,remaining_output=30)
                self.assertEqual(len(result['new_ids']),mismatch-known+2)
                self.assertEqual(result['feature_row'],mismatch)
                future=prefix+result['new_ids']
                next_grid,_=proposal_inputs(future,origin=3,proposals=list(range(30,37)))
                self.assertEqual(next_grid.start,11 if mismatch==7 else 3)
            result=accept_grid(known,inp,winners,remaining_output=30)
            self.assertEqual(len(result['new_ids']),9-known)
            self.assertEqual(result['accepted_draft_count'],8-known)
    def test_cap_eos_and_anchor_not_recounted(self):
        inp=list(range(20,28));winners=list(range(21,29))
        self.assertEqual(accept_grid(1,inp,winners,remaining_output=1)['new_ids'],[21])
        self.assertEqual(accept_grid(1,inp,winners,remaining_output=1)['accepted_draft_count'],1)
        r=accept_grid(1,inp,winners,remaining_output=10,eos_ids=(23,))
        self.assertEqual(r['new_ids'],[21,22,23]);self.assertEqual(r['finish'],'EOS');self.assertEqual(r['accepted_draft_count'],3)
        self.assertEqual(accept_grid(8,inp,winners,remaining_output=10)['new_ids'],[28])
    def test_future_does_not_define_reference_and_edge_never_shrinks_shape(self):
        confirmed=[1]*8189
        with self.assertRaises(ValueError):proposal_inputs(confirmed,origin=8180,proposals=[2]*7)
        with self.assertRaises(ValueError):proposal_inputs([1,2],origin=1,proposals=[])
        with self.assertRaises(ValueError):accept_grid(1,[1]*8,[1]*8,remaining_output=0)

if __name__=='__main__':unittest.main()
