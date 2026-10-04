import unittest
from block_prefill_reuse import logical_bound


class LogicalReuse(unittest.TestCase):
    def test_loading_is_required_service_not_ready(self):
        out=logical_bound([[0,1,2,3],[0,1,4,5]], [0], [1],
                          [{'expert':e} for e in [1,2,3,1,4,5]], 10)
        self.assertEqual(out['minimum_required_service_bytes'],50)
        self.assertEqual(out['minimum_future_initiation_bytes'],40)
        self.assertEqual(out['repeated_selected_loads'],1)
        self.assertEqual(out['tile_reuse_distance_histogram'],{1:2})

    def test_preload_not_consumed_is_separate(self):
        out=logical_bound([[0,1,2,3]], [], [], [{'expert':e} for e in range(5)],10)
        self.assertEqual(out['loads_not_consumed_in_this_phase'],1)
        self.assertEqual(out['minimum_required_service_bytes'],40)
        self.assertEqual(out['observed_logical_bytes'],50)

    def test_ready_evicted_and_reloaded_is_visible(self):
        out=logical_bound([[0,1,2,3]], [0], [], [{'expert':0}],10)
        self.assertEqual(out['initially_ready_selected_reload_count'],1)
        self.assertEqual(out['minimum_required_service_bytes'],30)

    def test_invalid_routes_and_contradictory_state_fail(self):
        for tiles,ready,loading in [([],[],[]),([[0,0,2,3]],[],[]),
                                     ([[0,1,2]],[],[]),([[0,1,2,3]],[0],[0])]:
            with self.assertRaises(ValueError):logical_bound(tiles,ready,loading,[],10)


if __name__=='__main__':unittest.main()
