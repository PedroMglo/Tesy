import unittest

from c2_gate import GateError
from c8_boundary_gate import preload_issued


class PreloadActivationTests(unittest.TestCase):
    def test_exact_activation_control(self):
        self.assertEqual(preload_issued("preloads issued = 0 (ready on arrival = 1)", False), 0)
        self.assertEqual(preload_issued("preloads issued = 17 (ready on arrival = 8)", True), 17)

    def test_missing_duplicate_or_wrong_activation_fails(self):
        for log, enabled in (("", True), ("preloads issued = 0", True),
                             ("preloads issued = 7", False),
                             ("preloads issued = 7\npreloads issued = 7", True)):
            with self.subTest(log=log, enabled=enabled), self.assertRaises(GateError):
                preload_issued(log, enabled)
