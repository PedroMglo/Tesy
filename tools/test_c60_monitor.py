"""Regression for C60's valid terminal sample being mistaken for a late start."""
from copy import deepcopy
import unittest

from run_bounded import prospective_endpoint_reason


class EndpointTests(unittest.TestCase):
    def test_observed_c60_timestamps_are_valid(self):
        resources={'cgroup':{'memory_max_bytes':18*2**30}}
        start={'events':{'max':0,'oom':0,'oom_kill':0},
               'events_local':{'max':0,'oom':0,'oom_kill':0}}
        end={'memory_max':18*2**30,'swap_max':0,'swap_current':0,
             'events':deepcopy(start['events']),
             'events_local':deepcopy(start['events_local'])}
        self.assertIsNone(prospective_endpoint_reason(.071,4.685,5.268,end,start,resources))
        self.assertEqual(prospective_endpoint_reason(2.001,4.685,5.268,end,start,resources),
                         'PROSPECTIVE_ENDPOINT_TELEMETRY_MISSING')
        self.assertEqual(prospective_endpoint_reason(.071,2.9,5.268,end,start,resources),
                         'PROSPECTIVE_ENDPOINT_TELEMETRY_MISSING')
        changed=deepcopy(end);changed['memory_max']-=1
        self.assertEqual(prospective_endpoint_reason(.071,4.685,5.268,changed,start,resources),
                         'PROSPECTIVE_CGROUP_END_INVALID')
        changed=deepcopy(end);changed['events']['oom']=1
        self.assertEqual(prospective_endpoint_reason(.071,4.685,5.268,changed,start,resources),
                         'PROSPECTIVE_CGROUP_END_EVENT')


if __name__=='__main__':unittest.main()
