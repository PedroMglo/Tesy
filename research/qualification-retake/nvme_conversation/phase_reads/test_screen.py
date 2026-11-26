import unittest

from screen import KEYS, Phase, Sample, extrema


def sample(lo, hi, count):
    return Sample(lo, hi, tuple(count * (i + 1) for i in range(len(KEYS))))


class Bounds(unittest.TestCase):
    def test_common_offset_includes_threshold_equalities_and_all_cells(self):
        rows = [sample(i * 6, i * 6 + 3, i * i) for i in range(10)]
        phase = Phase(11, 16, 33, 37)
        got = extrema(rows, phase, 11)
        independently_enumerated = []
        for shift in range(12):
            inner = [x.counters[0] for x in rows if x.lo + shift >= 16 and x.hi + shift <= 33]
            prior = [x.counters[0] for x in rows if x.hi + shift <= 11]
            later = [x.counters[0] for x in rows if x.lo + shift >= 37]
            independently_enumerated.append(
                (
                    max(inner) - min(inner) if inner else 0,
                    min(later) - max(prior) if prior and later else None,
                )
            )
        self.assertEqual(
            got["counters"]["read_bytes"]["min"], min(x[0] for x in independently_enumerated)
        )
        self.assertIsNone(got["counters"]["read_bytes"]["max"])
        self.assertTrue(any(x[1] is None for x in independently_enumerated))

    def test_closed_edges_and_different_counter_units(self):
        rows = [sample(i * 5, i * 5 + 1, i) for i in range(9)]
        b = extrema(rows, Phase(6, 8, 23, 26), 2)["counters"]
        self.assertEqual(b["read_bytes"], {"min": 2, "max": 5})
        self.assertEqual(b["rchar"], {"min": 4, "max": 10})
        self.assertEqual(b["syscr"], {"min": 6, "max": 15})

    def test_single_interior_observation_only_supports_zero(self):
        counters = extrema([sample(9, 11, 10)], Phase(2, 3, 12, 13), 0)["counters"]
        self.assertEqual(counters["read_bytes"], {"min": 0, "max": None})


if __name__ == "__main__":
    unittest.main()
