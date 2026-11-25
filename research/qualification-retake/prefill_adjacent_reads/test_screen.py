import unittest

from screen import ALIGN, SIZE, adjacent_runs, aligned_length


class AdjacencyTest(unittest.TestCase):
    def test_transitive_neighbors_do_not_prove_a_common_dispatch(self):
        keys = [(0, i, i, 1) for i in range(3)]
        first = {k: (0, 0, 0, "demand", t) for k, t in zip(keys, [1, 2, 5], strict=True)}
        dequeued = dict(zip(keys, [4, 6, 7], strict=True))
        self.assertEqual(adjacent_runs(keys, first, dequeued, True), [keys[:2], keys[2:]])
        self.assertEqual(adjacent_runs(keys, first, dequeued, False), [keys])

    def test_alignment_savings_are_only_padding(self):
        first = aligned_length(ALIGN, SIZE)
        second = aligned_length(ALIGN + SIZE, SIZE)
        grouped = aligned_length(ALIGN, 2 * SIZE)
        self.assertGreaterEqual(grouped, 2 * SIZE)
        self.assertEqual(first + second - grouped, ALIGN)


if __name__ == "__main__":
    unittest.main()
