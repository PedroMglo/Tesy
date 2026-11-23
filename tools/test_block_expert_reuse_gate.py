import copy
import unittest
from block_expert_reuse_gate import inspect, UNIONS


class NativeReuse(unittest.TestCase):
    def receipt(self, layer=0, mode='numeric-B'):
        candidate = mode.endswith('B')
        union, upper = UNIONS[layer]
        count = union if candidate else upper
        initial = dict(slot_expert=[-1]*40, slot_state=[0]*40,
                       slot_generation=[0]*40, demand_loads=0, preload_loads=0,
                       waves=0, wait_union_us=0, logical_bytes_per_load=13219200,
                       cache_bytes=528768000)
        final = copy.deepcopy(initial)
        final.update(slot_expert=list(range(40)), slot_state=[2]*40,
                     slot_generation=[count//40+(i<count%40) for i in range(40)],
                     demand_loads=count, waves=5, wait_union_us=12000)
        return dict(status='PASS_SELECTED_REUSE_NUMERIC', mode=mode, layer=layer,
                    slots=40, threads=8, wave_capacity=18,
                    original_tile_shapes=[32,32,29], groups=[93] if candidate else [32,32,29],
                    waves_by_group=[8] if candidate else [8,8,7],
                    outputs=[dict(phase=p, tokens=n, bitwise=True, nonfinite=0, max_abs=0)
                             for p,n in zip(['prefill0','prefill128','prefill_final'],[32,32,29])],
                    consumer_byte_combinations=count, service_wall_s=.25,
                    direct_reader=True, logical_bytes_not_NVMe_traffic=True,
                    initial=initial, final=final)

    def test_all_selected_layers_and_original_groups(self):
        for layer in UNIONS:
            for mode in ['numeric-A','numeric-B']:
                out=inspect(self.receipt(layer,mode),layer,mode)
                self.assertEqual(out['witness_components'],6*UNIONS[layer][mode.endswith('A')])

    def test_missing_byte_witness_tile_profile_or_nonfinite_rejected(self):
        for defect in ['output','witness','profile','nan','bytes','finite','worker','generation','reader','stale','duplicate']:
            value=self.receipt()
            if defect=='output':value['outputs'].pop()
            if defect=='witness':value['consumer_byte_combinations']-=1
            if defect=='profile':value['groups']=[32,32,29]
            if defect=='nan':value['service_wall_s']=float('nan')
            if defect=='bytes':value['final']['logical_bytes_per_load']+=1
            if defect=='finite':value['outputs'][0]['nonfinite']=1
            if defect=='worker':value['final']['slot_state'][0]=1
            if defect=='generation':value['final']['slot_generation'][0]-=1
            if defect=='reader':value['direct_reader']=False
            if defect=='stale':value['final']['slot_generation'][0]=0
            if defect=='duplicate':value['final']['slot_expert'][1]=0
            with self.assertRaises(ValueError):inspect(value,0,'numeric-B')

    def test_preloads_count_as_real_loads_not_free(self):
        value=self.receipt();value['final']['preload_loads']=20;value['final']['demand_loads']-=20
        self.assertEqual(inspect(value,0,'numeric-B')['actual_loads'],79)

    def test_loop_reorder_with_reloads_is_not_shared_union_service(self):
        value=self.receipt();value['final']['demand_loads']+=1;value['final']['slot_generation'][0]+=1
        with self.assertRaises(ValueError):inspect(value,0,'numeric-B')


if __name__=='__main__':unittest.main()
