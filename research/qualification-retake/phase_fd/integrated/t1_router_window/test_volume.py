import importlib.util
import unittest
from pathlib import Path

s = importlib.util.spec_from_file_location("router_tested", Path(__file__).with_name("volume.py"))
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
row = m.src.fd.Row(*([0] * len(m.src.fd.Row._fields)))


def make():
    meta = {(0, i): (8192 * i, 16) for i in range(3)}

    def r(kind, **kw):
        return row._replace(
            **(
                {
                    "kind": kind,
                    "layer": 0,
                    "slot": 0,
                    "expert": 0,
                    "gen": 1,
                    "wave": -1,
                    "call": 2,
                    "tile": 1,
                }
                | kw
            )
        )

    events = [r(5, expert=-1, gen=0), r(9), r(27, a=0), r(11, a=-1), r(12, a=2), r(13)]
    for i in range(3):
        events.extend(
            [
                r(15, component=i, a=8192 * i, b=4096, c=4096, begin=i * 10, ns=i * 10 + 4),
                r(16, component=i, a=16, b=0, begin=i * 10 + 4, ns=i * 10 + 9),
            ]
        )
    events.extend([r(17, ns=30), r(10), r(20), r(23), r(2)])
    return events, meta


class Volume(unittest.TestCase):
    def test_charged_preload_on_correct_generation(self):
        events, meta = make()
        key = (0, 0, 1, 0)
        work = m.consumed(events, meta)
        self.assertEqual(len(work), 1)
        self.assertEqual(work[key][1:], (2, (2, 1, 0, -1), 48, 12288))
        self.assertEqual(m.subtotal(work, {key}, {"47": 10})["totals"]["payload"], 0)
        self.assertEqual(
            m.subtotal(work, set(), {"47": 48})["denominators"]["47"]["decision"],
            "NO_GO_FIXED_DIRECT_GEOMETRY",
        )

    def test_demand_stale_early_or_rank_changed(self):
        events, meta = make()
        for i, r in enumerate(events):
            if r.kind not in (10, 16, 17, 27):
                continue
            edit = (
                dict(gen=99) if r.kind == 10 else dict(a=999) if r.kind in (16, 27) else dict(ns=2)
            )
            altered = events[:i] + [r._replace(**edit)] + events[i + 1 :]
            with self.assertRaises(ValueError):
                m.consumed(altered, meta)

    def test_distinct_generations_of_one_key_and_unconsumed_preload(self):
        seq = (2, 1, 0, 0)
        later = (2, 2, 0, 0)
        work = {
            (0, 2, 1, 7): (seq, 2, None, 48, 100),
            (0, 2, 3, 7): (seq, 2, later, 48, 101),
            (0, 5, 9, 7): (later, 0, later, 48, 102),
        }
        out = m.subtotal(work, {(0, 2, 3, 7)}, {"47": 45})
        self.assertEqual(out["totals"]["payload"], 48)
        self.assertEqual(out["totals"]["whole_fd"], 202)
        self.assertEqual(out["totals"]["l2_hits"], 1)
        self.assertEqual(out["totals"]["subsequent_tile"], 1)
        self.assertEqual(out["totals"]["never_consumed"], 1)
        self.assertEqual(out["denominators"]["47"]["decision"], "NO_GO_VOLUME_PAYLOAD")


if __name__ == "__main__":
    unittest.main()
