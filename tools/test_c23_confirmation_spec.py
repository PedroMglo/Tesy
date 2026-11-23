import unittest

from c23_prefix_confirm import SPEC


class ConfirmationSpecTest(unittest.TestCase):
    def test_three_new_alternating_pairs(self):
        self.assertEqual(len(SPEC), 6)
        self.assertEqual([row[1] for row in SPEC],
                         ['off', 'on', 'on', 'off', 'off', 'on'])
        self.assertEqual([row[2:4] for row in SPEC],
                         [('P1', 1), ('P1', 2), ('P2', 1), ('P2', 2),
                          ('P3', 1), ('P3', 2)])
        self.assertEqual(len({row[0] for row in SPEC}), 6)
        self.assertTrue(all(row[0].startswith('c23-') for row in SPEC))
