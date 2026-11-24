import unittest

from select_slots import simultaneous


class EndpointMatching(unittest.TestCase):
    def test_disjoint_paths_and_shared_endpoints(self):
        edges = [(20, 25), (2, 10), (10, 20), (12, 18)]
        self.assertEqual(simultaneous(edges), [(2, 10), (12, 18), (20, 25)])

    def test_reject_ambiguous_ownership(self):
        with self.assertRaises(ValueError):
            simultaneous([(1, 2), (1, 3)])
