import unittest

from c8_timing_gate import classify


class PreloadDecisionTests(unittest.TestCase):
    def test_medium_requires_prefill_and_work_with_decode_guard(self):
        pairs=[{"gains_pct":{"prefill_s":11}}, {"gains_pct":{"prefill_s":13}}]
        med={"prefill_s":12,"work_s":10,"tpot_aggregate_s":-4}
        self.assertEqual(classify("screen496",pairs,med),"SCREEN496_GO")
        self.assertEqual(classify("screen496",pairs,{**med,"work_s":7.9}),
                         "NO_GO_PRELOAD_SCREEN496")
        self.assertEqual(classify("screen496",pairs,{**med,"tpot_aggregate_s":-5.1}),
                         "NO_GO_PRELOAD_SCREEN496")
        negative=[pairs[0],{"gains_pct":{"prefill_s":-1}}]
        self.assertEqual(classify("screen496",negative,med),"NO_GO_PRELOAD_SCREEN496")

    def test_confirmation_excludes_a_negative_pair_and_decode_regression(self):
        pairs=[{"gains_pct":{"work_s":14}}, {"gains_pct":{"work_s":12}},
               {"gains_pct":{"work_s":11}}]
        med={"prefill_s":13,"work_s":12,"tpot_aggregate_s":-4}
        self.assertEqual(classify("confirm496",pairs,med),"CONFIRM496_GO")
        negative=pairs[:2]+[{"gains_pct":{"work_s":-1}}]
        self.assertEqual(classify("confirm496",negative,med),"NO_GO_PRELOAD_CONFIRM496")
        self.assertEqual(classify("confirm496",pairs,{**med,"tpot_aggregate_s":-5.1}),
                         "NO_GO_PRELOAD_CONFIRM496")
