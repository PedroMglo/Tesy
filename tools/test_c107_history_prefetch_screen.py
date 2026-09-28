import unittest
from collections import defaultdict

from c107_history_prefetch_screen import evaluate


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


if __name__=='__main__':unittest.main()
