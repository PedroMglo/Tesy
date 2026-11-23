"""C73 frozen input and paired timing decision controls, no model."""
import tempfile
from pathlib import Path
import unittest

from c2_gate import GateError
from c73_wave_timing_run import ARMS, gains, ids, run_id


INPUT = Path('results/c73-wave-timing-20260928T1713Z')


class C73WaveTiming(unittest.TestCase):
    def test_input_is_frozen_c52b_ids(self):
        row = ids(INPUT)
        self.assertEqual([len(row[x]) for x in
            ('cold513','warm_prefix2043','warm_tail154','continuation32')],
            [513,2043,154,32])

    def test_pair_gain_and_logit_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'raw').mkdir()
            receipts = []
            for case,pair,wave in ARMS:
                name = run_id(case,pair,wave)
                (root/'raw'/(name+'.f32')).write_bytes(b'full-logit-control')
                timing = {'work':100.0 if wave=='off' else 90.0,
                          'prefill':60.0 if wave=='off' else 54.0,
                          'decode32':40.0 if wave=='off' else 36.0}
                receipts.append({'run_id':name,'source':{'timing_s':timing}})
            report = gains(root,{},receipts)
            for case in ('cold513','warm154'):
                self.assertEqual(report['decision_by_case'][case]['status'],
                                 'SCREEN_GO_CONFIRMATION_PENDING')
                self.assertEqual(report['decision_by_case'][case]
                                 ['median_pair_gain_percent']['work'],10.0)
            (root/'raw'/(run_id('warm154',2,'on')+'.f32')).write_bytes(b'mismatch')
            with self.assertRaisesRegex(GateError,'FAIL_SAME_PROFILE_FIDELITY'):
                gains(root,{},receipts)


if __name__ == '__main__':
    unittest.main()
