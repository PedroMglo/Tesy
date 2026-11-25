import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("t1_screen", Path(__file__).with_name("screen.py"))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def row(kind, expert, gen, old, call):
    return SimpleNamespace(
        kind=kind, expert=expert, gen=gen, a=old, layer=0, slot=0, call=call, c=s.T
    )


def trace():
    rows = [row(5, 1, 1, 2, 1)]
    for i, (key, old, call) in enumerate(((2, 1, 2), (1, 2, 2), (3, 1, 3), (2, 3, 3)), 2):
        if call == 3 and i == 4:
            rows.append(row(2, -1, 0, 0, 2))
        for k in (11, 10, 13, 15, 17):
            rows.append(row(k, key, i, old, call))
    return rows


class WarmSelection(unittest.TestCase):
    def test_selection_applied_before_claims_and_joint_prices(self):
        data = trace()
        for f in ("publication", "victims"):
            model = s.Policy(f, 3, [(0, 2)])
            out = s.simulate(data, model)
            self.assertIn((0, 0, 2, 2), model.hits)
            self.assertEqual(out["decode_jobs"], 2)
            self.assertEqual(out["decode_hits"], 1)
            self.assertEqual(out["remaining_prefill_bytes"], s.T if f == "publication" else 0)
            groups = [[((0, 0, 2, 2), 90), ((0, 0, 4, 3), 40)]]
            self.assertEqual(s.price(groups, model.hits, 7)["first_at_1_ns"], 47)
            self.assertEqual(s.price(groups, model.hits, 7)["first_at_4_5_ns"], 39)
        self.assertEqual(
            s.eligible_sets(data), {"publication": {(0, 1), (0, 2)}, "victims": {(0, 2)}}
        )

    def test_cold_ablation_and_eviction_not_all_future_is_free(self):
        data = trace()
        for f in ("victims", "publication"):
            model = s.Policy(f, 1, [])
            out = s.simulate(data, model)
            self.assertNotIn((0, 0, 2, 2), model.hits)
            self.assertEqual(out["remaining_prefill_bytes"], s.T if f == "victims" else 2 * s.T)
            self.assertEqual(out["decode_jobs"], 2)
        self.assertNotEqual(s.fingerprint([[0, 1], [0, 2]]), s.fingerprint([[0, 2], [0, 1]]))


if __name__ == "__main__":
    unittest.main()
