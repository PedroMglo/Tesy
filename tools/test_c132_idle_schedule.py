import unittest

from c2_gate import GateError
from c2_server_run import session_idle_schedule


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


if __name__ == '__main__':
    unittest.main()
