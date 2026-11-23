import unittest
from collections import defaultdict

from c107_history_prefetch_screen import evaluate, historical_status, HISTORICAL_TRACE_SHA


class HistoryPrefetch(unittest.TestCase):
    def test_repeated_route_does_not_imply_absent_miss_coverage(self):
        selected=defaultdict(set)
        absent=defaultdict(set)
        for token in range(32):
            for layer in range(36):
                selected[(token,layer)]={1,2,3,4}
                absent[(token,layer)]={9}
        result=evaluate(selected,absent,1)
        self.assertEqual(result['absent_demands_covered'],0)
        self.assertEqual(result['selected_route_coverage_fraction'],1.0)

    def test_absent_expert_in_previous_set_is_covered(self):
        selected=defaultdict(set)
        absent=defaultdict(set)
        for token in range(32):
            for layer in range(36):
                selected[(token,layer)]={1,2,3,4}
                absent[(token,layer)]={4}
        result=evaluate(selected,absent,1)
        self.assertEqual(result['absent_demands_covered'],31*36)
        self.assertEqual(result['absent_coverage_fraction'],1.0)

    def test_historical_verdict_is_bound_to_trace_and_metrics(self):
        results=[{'history_tokens':h,'absent_demands_covered':covered}
                 for h,covered in zip((1,2,4,8),(0,0,0,2))]
        self.assertEqual(historical_status(HISTORICAL_TRACE_SHA,results),
                         'NO_GO_RECENT_HISTORY_PREFETCH_ON_C105_DECODE')
        results[0]['absent_demands_covered']=100
        self.assertEqual(historical_status(HISTORICAL_TRACE_SHA,results),
                         'ANALYSIS_ONLY_NO_PROSPECTIVE_THRESHOLD')
        results[0]['absent_demands_covered']=0
        self.assertEqual(historical_status('0'*64,results),
                         'ANALYSIS_ONLY_NO_PROSPECTIVE_THRESHOLD')


if __name__=='__main__':unittest.main()
