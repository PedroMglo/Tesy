"""Negative controls for the real wave boundary and the conditional price."""

import copy
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RUN = run_path(HERE / "run.py")
OBS = run_path(HERE / "observe.py")


class Owner(unittest.TestCase):
    def test_readiness_is_clipped_at_entry_and_at_the_last_other_weight(self):
        target, peer = (14, 14, 7, 54), (14, 12, 5, 107)
        wait = [120, 200, [[target, 80, 180], [peer, 100, 170]]]
        self.assertEqual(OBS["cut_price"](wait, {target}), 10)
        self.assertEqual(OBS["cut_price"](wait, {target, peer}), 60)
        self.assertEqual(OBS["cut_price"]([120, 120, []], {target}), 0)

    def test_real_pin_and_remap_gates_reject_mutations(self):
        spec = RUN["truth"]()
        waves = [
            dict(w, begin=10000 + i * 2000, end=11800 + i * 2000)
            for i, w in enumerate(spec["waves"])
        ]
        jobs = [
            dict(
                reservation=r,
                tid=i % 4 + 200,
                read=[10001 + i, 10120 + i],
                sets=[[10121 + i, 10130 + i], [10140 + i, 10150 + i], [10160 + i, 10180 + i]],
                publication=10200 + i,
                from_ram=False,
            )
            for i, r in enumerate(spec["order"])
        ]
        baseline = dict(source_replaced=1, mode="R", jobs=jobs, waves=waves)
        self.assertEqual(RUN["local"](baseline, spec)["workers"], 4)
        stale = copy.deepcopy(baseline)
        stale["waves"][1]["pins"][0][2] -= 1
        with self.assertRaisesRegex(ValueError, "pins"):
            RUN["local"](stale, spec)
        wrong = copy.deepcopy(baseline)
        wrong["waves"][1]["remap"][0] += 1
        with self.assertRaisesRegex(ValueError, "remap"):
            RUN["local"](wrong, spec)
        late = copy.deepcopy(baseline)
        late["jobs"][-1]["publication"] = 10**9
        with self.assertRaisesRegex(ValueError, "unpublished weight"):
            RUN["local"](late, spec)


if __name__ == "__main__":
    unittest.main()
