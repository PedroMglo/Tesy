import unittest

from c2_gate import GateError
from c53b_session_cost import at


class SessionCostTerminalTests(unittest.TestCase):
    def test_terminal_counter_is_lower_bound_without_extrapolation(self):
        rows = [{'elapsed_s':0.0,'proc':{'read_bytes':100}},
                {'elapsed_s':1.0,'proc':{'read_bytes':300}}]
        self.assertEqual(at(rows,0.5,'read_bytes'),200)
        self.assertEqual(at(rows,1.4,'read_bytes'),300)

    def test_rejects_gap_over_two_seconds(self):
        rows = [{'elapsed_s':0.0,'proc':{'read_bytes':100}},
                {'elapsed_s':1.0,'proc':{'read_bytes':300}}]
        with self.assertRaises(GateError):
            at(rows,3.01,'read_bytes')

    def test_rejects_missing_terminal_counter(self):
        rows = [{'elapsed_s':0.0,'proc':{'read_bytes':100}},
                {'elapsed_s':1.0,'proc':{}}]
        with self.assertRaises(GateError):
            at(rows,1.4,'read_bytes')
