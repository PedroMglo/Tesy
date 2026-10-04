import copy
import unittest
import test_block_expert_reuse_gate as fixtures
from block_expert_reuse_timing import evaluate,LAYERS,MODES

class TimingBoundary(unittest.TestCase):
    def rows(self):
        fixture=fixtures.NativeReuse();rows=[]
        for layer in LAYERS:
            for mode,t in zip(MODES,(2.,1.5,1.4,1.9)):
                v=fixture.receipt(layer,mode.replace('timing','numeric'))
                v.update(mode=mode,status='MEASURED_SELECTED_REUSE_SERVICE',consumer_byte_combinations=0,service_wall_s=t);rows.append(v)
        return rows
    def test_actual_service_pairs_and_load_elimination(self):
        value=evaluate(self.rows());self.assertEqual(value['decision'],'GO_SELECTED_OPERATOR_REUSE')
        self.assertAlmostEqual(value['layers'][0]['median_service_gain_percent'],(25+100*.5/1.9)/2)
        rows=self.rows();rows[1]['service_wall_s']=3.
        self.assertEqual(evaluate(rows)['decision'],'MIXED_OR_NO_GO_SELECTED_OPERATOR_REUSE')
    def test_missing_wrong_layer_empty_outputs_and_nan_are_not_zero(self):
        with self.assertRaises(ValueError):evaluate(self.rows()[:-1])
        for key,replacement in [('outputs',[]),('layer',24),('service_wall_s',float('nan')),('consumer_byte_combinations',79)]:
            rows=self.rows();rows[1][key]=replacement
            with self.assertRaises(ValueError):evaluate(rows)

if __name__=='__main__':unittest.main()
