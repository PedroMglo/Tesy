import unittest

from c2_gate import GateError
from c53_session_cost import at


class SessionCostAccountingTests(unittest.TestCase):
    def test_interpolates_cumulative_counter(self):
        rows = [{'elapsed_s':0.0,'proc':{'read_bytes':100}},
                {'elapsed_s':2.0,'proc':{'read_bytes':300}}]
        self.assertEqual(at(rows,1.0,'read_bytes'),200)

    def test_rejects_counter_reset_or_missing_interval(self):
        for rows in (
            [{'elapsed_s':0.0,'proc':{'read_bytes':300}},
             {'elapsed_s':2.0,'proc':{'read_bytes':100}}],
            [{'elapsed_s':0.0,'proc':{'read_bytes':100}},
             {'elapsed_s':4.0,'proc':{'read_bytes':300}}],
        ):
            with self.subTest(rows=rows), self.assertRaises(GateError):
                at(rows,1.0,'read_bytes')

    def test_rejects_unbracketed_boundary(self):
        rows = [{'elapsed_s':0.0,'proc':{'rchar':0}},
                {'elapsed_s':1.0,'proc':{'rchar':1}}]
        with self.assertRaises(GateError):
            at(rows,1.1,'rchar')
