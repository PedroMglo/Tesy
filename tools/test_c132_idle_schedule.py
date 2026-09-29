import unittest

from c2_gate import GateError
from c2_server_run import require_natural_completion, session_idle_schedule


class IdleScheduleTest(unittest.TestCase):
    def test_legacy_constant(self):
        self.assertEqual(session_idle_schedule({'inter_request_idle_s': 165}, 3),
                         [0.0, 165.0, 165.0])

    def test_active_then_spaced(self):
        config = {'inter_request_idle_s': 0,
                  'inter_request_idle_schedule_s': [0, 0, 0, 600, 570]}
        self.assertEqual(session_idle_schedule(config, 5),
                         [0.0, 0.0, 0.0, 600.0, 570.0])

    def test_invalid_schedule(self):
        for schedule in ([0, 1], [1, 0, 0], [0, True, 0],
                         [0, float('nan'), 0], [0, 601, 0], [0, -1, 0]):
            with self.subTest(schedule=schedule), self.assertRaises(GateError):
                session_idle_schedule({'inter_request_idle_schedule_s': schedule}, 3)

    def test_natural_completion_gate(self):
        good={'id':'turn','finish_reason':'stop','usage':{'completion_tokens':767}}
        require_natural_completion(good,768)
        for reason,count in [('length',767),('stop',768),('stop',0)]:
            with self.subTest(reason=reason,count=count), self.assertRaises(GateError):
                require_natural_completion({'id':'turn','finish_reason':reason,
                                            'usage':{'completion_tokens':count}},768)


if __name__ == '__main__':
    unittest.main()
