import unittest
from block_grid_contract import reference_inputs, retention_after_rejection, require_greedy


class DraftIndependentGrid(unittest.TestCase):
    def test_prefix_alone_defines_padding_query_and_completed_grids(self):
        prefix=[11,12,13,20,21,22,23,24,25]
        grid=reference_inputs(prefix,origin=3,B=4)
        self.assertEqual(grid.completed_grids,((20,21,22,23),))
        self.assertEqual(grid.inputs,(24,25,0,0))
        self.assertEqual((grid.start,grid.query_row),(7,1))
        # There is deliberately no draft argument: a proposed future cannot
        # influence the reference construction.
        with self.assertRaises(TypeError): reference_inputs(prefix,origin=3,B=4,draft=[999])

    def test_every_partial_rejection_rebuilds_same_grid_from_confirmed_only(self):
        for known in range(1,5):
            grid=reference_inputs([11,12,13]+list(range(20,20+known)),origin=3,B=4)
            self.assertEqual(grid.inputs,tuple(range(20,20+known))+(0,)*(4-known))
            self.assertEqual(retention_after_rejection(grid_start=3,confirmed_after=3+known,B=4),3)

    def test_full_grid_bonus_begins_new_grid(self):
        grid=reference_inputs([11,12,13,20,21,22,23,24],origin=3,B=4)
        self.assertEqual(grid.inputs,(24,0,0,0))
        self.assertEqual(grid.start,7)
        self.assertEqual(grid.completed_grids,((20,21,22,23),))

    def test_context_edge_and_invalid_input_do_not_change_shape(self):
        reference_inputs([1]*8185,origin=8180,B=8,context=8192)
        with self.assertRaises(ValueError): reference_inputs([1]*8189,origin=8180,B=8,context=8192)
        with self.assertRaises(ValueError): reference_inputs([],origin=3,B=4)
        with self.assertRaises(ValueError): reference_inputs([1,2,3,-1],origin=3,B=4)

    def test_sampling_is_rejected_before_candidate_execution(self):
        require_greedy(temperature=0)
        for temp in (1,.1,'0',float('nan')):
            with self.assertRaises(ValueError): require_greedy(temperature=temp)


if __name__=='__main__': unittest.main()
