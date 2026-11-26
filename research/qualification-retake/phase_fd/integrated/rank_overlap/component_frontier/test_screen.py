import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

S = run_path(str(Path(__file__).with_name("screen.py")))
Wave = S["P"]["OVERLAP"]["Wave"]


class Bounds(unittest.TestCase):
    def test_parking_mixed_and_unfenced(self):
        w = Wave(1, 1, 0, 0, 1, 10, 50, [])
        self.assertEqual(set(S["credits"](w, None, {})[0].values()), {0})
        w.demand = [1, 2]
        r = {1: (0, 0, 0), 2: (40, 30, 20)}
        self.assertEqual(set(S["credits"](w, None, r)[0].values()), {30})
        r[1] = (35, 25, 20)
        gain, pending, gap, _ = S["credits"](w, None, r)
        self.assertEqual((pending, gap, list(gain.values())), (True, None, [5, 15, 20, 30]))
        r[1] = (40, 30, 20)
        self.assertEqual(S["credits"](w, None, r)[0]["full"], 0)
        after = Wave(1, 1, 1, 0, 1, 52, 60, [])
        r[1] = (35, 25, 20)
        self.assertEqual(set(S["credits"](w, after, r)[0].values()), {2})
        after.begin = 49
        with self.assertRaises(ValueError):
            S["credits"](w, after, r)

    def test_wrong_availability(self):
        w = Wave(1, 1, 0, 0, 1, 10, 50, [1])
        for x in [(51, 30, 20), (45, 30, 40)]:
            with self.assertRaises(ValueError):
                S["credits"](w, None, {1: x})

    def test_components(self):
        def event(kind, comp, beg, end):
            return SimpleNamespace(
                kind=kind,
                layer=0,
                slot=0,
                gen=1,
                expert=1,
                c=13221888,
                component=comp,
                begin=beg,
                ns=end,
            )

        rows = [event(30, -1, 1, 9)] + [event(16, i, 10 + 2 * i, 11 + 2 * i) for i in range(3)]
        k = (0, 0, 1, 1)
        self.assertEqual(S["observations"](rows, {k: 20})[k], (20, 11, 9))
        for wrong in (rows[:-1], [rows[0], rows[2], rows[1], rows[3]]):
            with self.assertRaises(ValueError):
                S["observations"](wrong, {k: 20})


if __name__ == "__main__":
    unittest.main()
