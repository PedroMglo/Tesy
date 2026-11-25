import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen import Wave, opportunity, summarize  # noqa: E402


class RankBound(unittest.TestCase):
    def test_last_publish_and_useful_tail(self):
        w = Wave(2, 2, 15, 0, 32, 100, 200, ["hit", "slow"])
        n = Wave(2, 2, 15, 1, 32, 230, 350, [])
        s = opportunity(w, n, {"hit": 0, "slow": 170})
        self.assertEqual(
            (s["lead_ns"], s["resident_upper_ns"], s["progressive_upper_ns"]), (70, 30, 30)
        )
        self.assertEqual(opportunity(w, n, {"hit": 140, "slow": 170})["resident_upper_ns"], 0)
        self.assertEqual(opportunity(w, n, {"hit": 140, "slow": 170})["progressive_upper_ns"], 30)

    def test_boundary_or_pruned_router_grants_full_lead(self):
        w = Wave(2, 1, 34, 7, 32, 100, 200, ["a", "b"])
        for next_w in (None, Wave(2, 2, 0, 0, 32, 212, 225), Wave(2, 1, 35, -1, 0, 212, 225)):
            self.assertEqual(
                opportunity(w, next_w, {"a": 33, "b": 193})["progressive_upper_ns"], 93
            )
        with self.assertRaisesRegex(ValueError, "after remap"):
            opportunity(w, None, {"a": 33, "b": 201})

    def test_no_credit_all_ready_or_single(self):
        for keys in ([], ["a"], ["a", "b"]):
            w = Wave(3, 1, 18, -1, 1, 100, 200, keys)
            self.assertEqual(opportunity(w, None, {"a": 60, "b": 30})["progressive_upper_ns"], 0)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            opportunity(Wave(3, 1, 14, -1, 1, 100, 200, ["a", "a"]), None, {"a": 130})

    def test_own_first_cut_and_separate_decode(self):
        m = 10**6
        waves = [
            Wave(3, 1, 1, -1, 1, 10 * m, 11 * m, ["a", "b"]),
            Wave(4, 1, 2, -1, 1, 14 * m, 15 * m, ["c", "d"]),
        ]
        z = summarize(waves, {"a": 0, "b": 11 * m, "c": 13 * m, "d": 15 * m}, m, 10 * m, 14 * m)
        self.assertEqual(z["phase"]["first_final"]["progressive_upper_ns"], m)
        self.assertEqual(z["phase"]["decode"]["progressive_upper_ns"], 2 * m)


if __name__ == "__main__":
    unittest.main()
