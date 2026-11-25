import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

S = run_path(str(Path(__file__).with_name("screen.py")))


class Majority(unittest.TestCase):
    def test_geometry_strict_and_causal(self):
        for n, threshold in ((29, 15), (32, 17)):
            rows = [
                (9, 8, 1 if i < threshold else 6, 4 if i < threshold - 1 else 7) for i in range(n)
            ]
            votes, _, fixed, strict = S["decision"](rows, {9})
            self.assertEqual(strict, [8, 1, 7] if n == 29 else [8, 1])
            self.assertEqual(len(fixed), 4)
            self.assertEqual(votes[4], threshold - 1)
        rows = [[1, 2, 3, 4], [1, 2, 7, 8]]
        self.assertEqual(S["decision"](rows, set())[2:], ([1, 2, 3, 4], [1, 2]))
        with self.assertRaises(ValueError):
            S["decision"]([[6, 6, 8, 9]], set())

    def test_global_cursor_includes_false_offers(self):
        b = [(0, 0, "cold/32", [0], {}), (1, 1, "full/32", [9], {9: (3, 3, 4)})]
        w = S["W"]
        out = w["evaluate"](b, 10**9, 3)
        self.assertEqual(out["global"]["hits"], 1)
        self.assertEqual(out["by_target"]["full/32"]["barrier_fifo"], 0)
        self.assertEqual(w["evaluate"](b[1:], 10**9, 3)["global"]["barrier_fifo"], 1)

    def test_first_generation_and_ineligible_resident(self):
        def event(ns, a=0):
            return SimpleNamespace(ns=ns, a=a)

        dest = (1, 3, 1, 1)
        rs = [dict(expert=5, slot=1, gen=g, wave=0) for g in (1, 2)]
        rs += [dict(expert=9, slot=4, gen=1, wave=0)]
        cell = dict(reserves=rs, occupied={9}, last_pred=10)
        jobs, deadlines = {}, {}
        for r in rs:
            k = (1, r["slot"], r["gen"], r["expert"])
            jobs[k] = {
                11: (11, event(21)),
                12: (12, event(22, 2)),
                17: (18, event(30)),
                30: (17, event(28)),
            }
            deadlines[k] = (dest, (21, 23, 25))
        index = jobs, {(*dest, 5): 1}, {dest: 31}, []
        origins, eligible = S["first_origins"](3, 1, cell, event(20), deadlines, index)
        self.assertEqual(eligible, 2)
        self.assertEqual(origins[5]["key"], (1, 1, 1, 5))
        m = S["metrics"]([5, 7, 8], {}, origins, {5, 7}, 20)
        self.assertEqual((m["matches"], m["unused"], m["routed_no_new_read"]), (1, 1, 1))
        self.assertEqual(
            (m["origin_preload"], m["next_wave"], m["observed_read_by_barrier"]), (1, 1, 0)
        )
        index[2][dest] = 29
        with self.assertRaises(ValueError):
            S["first_origins"](3, 1, cell, event(20), deadlines, index)


if __name__ == "__main__":
    unittest.main()
