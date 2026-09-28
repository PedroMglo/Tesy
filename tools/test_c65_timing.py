"""Discriminants for paired-gain arithmetic and fresh-process fidelity."""
import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError
import c65_timing_run as c65


class TimingDecisionTest(unittest.TestCase):
    def fixture(self, root):
        (root/'raw').mkdir()
        receipts=[]
        # Pair gains are 10% and 0%, median 5%. A ratio of medians differs.
        for case in c65.CASES:
            for pair,p12,p14 in ((1,100.0,90.0),(2,200.0,200.0)):
                for ngl,work in ((12,p12),(14,p14)):
                    run=c65.run_id(case,pair,ngl)
                    (root/'raw'/(run+'.f32')).write_bytes(bytes([ngl]))
                    receipts.append({'run_id':run,'source':{'timing_s':{
                        'work':work,'prefill':work/2,'decode32':work/2}}})
        return receipts

    def test_pair_gain_uses_each_control_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); receipts=self.fixture(root)
            report=c65.gains(root,{},receipts)
            self.assertEqual(report['decision_by_case']['latency-medium']
                             ['median_pair_gain_percent']['work'],5.0)
            self.assertEqual(report['decision_by_case']['latency-medium']['status'],
                             'NO_GO_SCREEN496')  # second pair is not positive

    def test_fresh_process_mismatch_fails_before_timing_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); receipts=self.fixture(root)
            (root/'raw'/(c65.run_id('latency-medium',2,14)+'.f32')).write_bytes(b'changed')
            with self.assertRaisesRegex(GateError,'FAIL_SAME_PROFILE_FIDELITY'):
                c65.gains(root,{},receipts)


if __name__=='__main__':
    unittest.main()
