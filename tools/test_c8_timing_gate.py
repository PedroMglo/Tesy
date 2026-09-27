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
