import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

S = run_path(str(Path(__file__).with_name("score.py")))
Cut, size = S["Cut"], S["SIZE"]


def cuts(last, nxt):
    return {(1, 1, 1): [(last, last)], (1, 1, 2): [(nxt, nxt)]}


class Windows(unittest.TestCase):
    def test_volume_and_lanes(self):
        p = S["price"]([8_000_000] * 5, size // 16)
        self.assertEqual(p["partial_bytes_8"], size // 2)
        self.assertEqual(p["whole_jobs_8"], 0)
        self.assertEqual(p["partial_residual_ns_8"], 5 * size // 8 - size // 16)
        self.assertEqual(p["whole_residual_ns_8"], 5 * size // 8)
        self.assertEqual(p["read_residual_ns_1x"], 10_000_000 - size // 16)
        self.assertEqual(p["read_residual_ns_half"], 5_000_000 - size // 16)
        a = S["price"]([16], 100_000_000)
        b = S["price"]([16], 0)
        both = S["summarize"]([a, b])
        self.assertEqual(both["whole_jobs_8"], 1)
        self.assertEqual(both["partial_residual_ns_8"], size // 8)
        self.assertEqual(S["summarize"]([a])["partial_residual_ns_8"], 0)

    def test_horizon(self):
        prev = Cut((1, 1, 1, -1), 100, True, 20, 0)
        r = Cut((1, 1, 2, 0), 111, True, 20, 1)
        self.assertEqual(S["horizon"](cuts(prev, r), ([], []), r.site), ("drained", 11))
        self.assertEqual(S["horizon"](cuts(prev, r), ([99], [101]), r.site), ("occupied", 11))
        busy = Cut(prev.site, prev.ns, False, prev.epoch, prev.index)
        self.assertEqual(S["horizon"](cuts(busy, r), ([], []), r.site), ("occupied", 11))
        first = Cut((2, 1, 0, -1), 115, True, 20, 2)
        cells = cuts(prev, r) | {first.site[:3]: [(first, first)]}
        self.assertEqual(S["horizon"](cells, ([], []), first.site), ("layer0", 0))
        self.assertEqual(S["horizon"](cells, ([], []), (1, 1, 2, 1))[1], None)
        foreign = Cut(r.site, r.ns, True, r.epoch, 3)
        self.assertEqual(S["horizon"](cuts(prev, foreign), ([], []), r.site), ("noncontiguous", 11))

    def test_manager_state_and_missing_end(self):
        def r(kind, ns, layer=0, begin=0):
            return SimpleNamespace(
                kind=kind, ns=ns, call=1, tile=1, layer=layer, wave=-1, a=0, b=0, begin=begin
            )

        seq = [
            r(9, 1),
            r(11, 2),
            r(12, 3),
            r(13, 4),
            r(23, 5),
            r(30, 9, begin=5),
            r(17, 10),
            r(9, 11, 1),
            r(23, 12, 1),
        ]
        cells, idx = S["trace_cuts"](seq)
        self.assertEqual(S["horizon"](cells, idx, (1, 1, 1, -1)), ("occupied", 6))
        with self.assertRaises(ValueError):
            S["trace_cuts"](seq[:-1])
        with self.assertRaises(ValueError):
            S["trace_cuts"]([r(17, 2)])


if __name__ == "__main__":
    unittest.main()
