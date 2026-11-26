import unittest
from collections import Counter
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("screen.py")))
Wave = S["OVERLAP"]["Wave"]
opportunity = S["OVERLAP"]["opportunity"]


class TestRankEnvelope(unittest.TestCase):
    def test_frontier_and_fence(self):
        w = Wave(3, 1, 4, 0, 1, 100, 190, ["hit", "miss1", "miss2"])
        after = Wave(3, 1, 5, 0, 1, 210)
        ready = {"hit": 80, "miss1": 130, "miss2": 175}
        metrics = opportunity(w, after, ready)
        self.assertEqual(
            (metrics["lead_ns"], metrics["resident_upper_ns"], metrics["progressive_upper_ns"]),
            (75, 20, 20),
        )
        ready["hit"] = 120
        metrics = opportunity(w, None, ready)
        self.assertEqual((metrics["resident_upper_ns"], metrics["progressive_upper_ns"]), (0, 55))
        ready["miss2"] = 191
        with self.assertRaises(ValueError):
            opportunity(w, after, ready)
        w.demand = []
        self.assertEqual(opportunity(w, after, {})["progressive_upper_ns"], 0)

    def test_decode_only_and_shared_44(self):
        totals = {
            (p, t): Counter(resident_upper_ns=1, progressive_upper_ns=2)
            for p in S["PHASES"]
            for t in ("CPU", "CUDA0")
        }
        a = S["price_modes"](totals, 1000, 500)
        d = a["decode/CPU"]["progressive"]
        self.assertEqual((d["first_floor_ns"], d["decode_floor_ns"]), (998, 496))
        self.assertEqual(a["prefill_and_decode/CPU_and_CUDA"]["resident"]["first_floor_ns"], 994)


if __name__ == "__main__":
    unittest.main()
