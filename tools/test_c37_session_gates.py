"""Small negative controls for long session timing and prefix guards."""

import unittest

from c2_gate import GateError
from c2_server_run import session_idle_seconds, validate_adjacent_cache


class SessionGates(unittest.TestCase):
    def test_frozen_idle(self):
        self.assertEqual(session_idle_seconds({'inter_request_idle_s':180}),180.0)
        self.assertEqual(session_idle_seconds({}),0.0)
        for value in (-1, 601, float('inf'), float('nan'), '180', True):
            with self.subTest(value=value), self.assertRaises(GateError):
                session_idle_seconds({'inter_request_idle_s':value})

    def test_cache_hit_and_mutants(self):
        previous=list(range(65))
        current=list(range(60))+[999,1000,1001]
        self.assertEqual(validate_adjacent_cache(previous,current,60,60,5),60)
        for cache_n, minimum in ((0,60),(61,60),(60,61),(-1,60),('60',60)):
            with self.subTest(cache_n=cache_n, minimum=minimum), self.assertRaises(GateError):
                validate_adjacent_cache(previous,current,cache_n,minimum)
        with self.assertRaises(GateError):
            validate_adjacent_cache(previous,current,60,60,4)


if __name__=='__main__':
    unittest.main()
