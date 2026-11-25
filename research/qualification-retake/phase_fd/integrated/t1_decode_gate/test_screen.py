import importlib.util
import itertools
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "decode_joint_test", Path(__file__).with_name("screen.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
job = m.sf.Job


def price(regions, selection, a, b):
    costs = []
    for groups in regions:
        number = 0
        for jobs in groups:
            terms = [
                j.copies * b + (j.read * a if j.first and j.key not in selection else 0)
                for j in jobs
            ]
            number += max(sum(terms), 4 * max(terms))
        costs.append(number)
    return costs[0] + costs[1], costs[1] + costs[2]


class Joint(unittest.TestCase):
    def test_partition_matches_exhaustive_candidates_in_two_clocks(self):
        for seed in range(5):
            regions = [
                [
                    [
                        job(
                            (layer, i),
                            ((5 * i + 7 * layer + seed) % 9 + 1) * 10**8,
                            ((i + seed) % 3) * 1000,
                            i < 3,
                        )
                        for i in range(4)
                    ]
                ]
                for layer in range(3)
            ]
            eligible = {
                (layer, i) for layer in range(3) for i in range(3) if (i + layer + seed) % 4
            }
            f, d = 9 * 10**9, 7 * 10**9
            for a, b in ((1, 1), (4, 5)):
                den = 4 * b
                for k in range(1, len(eligible)):
                    choose, passing, _ = m.frontier(regions, eligible, k, a, b, f, d)

                    def cost(s, regions=regions, a=a, b=b, f=f, d=d, den=den):
                        n, v = price(regions, s, a, b)
                        return f * den + n, d * den + v

                    allcosts = [cost(s) for s in itertools.combinations(eligible, k)]
                    self.assertEqual(min(x[0] for x in allcosts), cost(choose("minimum_first"))[0])
                    self.assertEqual(min(x[1] for x in allcosts), cost(choose("minimum_decode"))[1])

                    def ratio(x):
                        return max(x[0] * m.DECODE, 6 * x[1] * m.FIRST)

                    self.assertEqual(
                        min(map(ratio, allcosts)), ratio(cost(choose("minimum_joint")))
                    )
                    self.assertEqual(
                        bool(passing),
                        any(x <= m.FIRST * den and 6 * y <= m.DECODE * den for x, y in allcosts),
                    )

    def test_two_feasible_separately_but_incompatible(self):
        unit = 10**9
        regions = ([[job((0, 0), unit, 0, True)]], [], [[job((1, 0), unit, 0, True)]])
        allowed = {(0, 0), (1, 0)}
        choose, passing, tested = m.frontier(regions, allowed, 1, 1, 1, 10 * unit, 7 * unit)
        self.assertEqual((passing, tested), (0, 2))
        self.assertNotEqual(choose("minimum_first"), choose("minimum_decode"))
        regions = (regions[0], [[job((2, 0), 2 * unit, 0, True)]], regions[2])
        choose, passing, _ = m.frontier(regions, allowed | {(2, 0)}, 1, 1, 1, 9 * unit, 6 * unit)
        self.assertEqual(passing, 1)
        self.assertEqual(choose("minimum_joint"), {(2, 0)})
        with self.assertRaisesRegex(ValueError, "duplicate first"):
            m.frontier((regions[0], regions[0], []), allowed, 1, 1, 1, 0, 0)

    def test_clock_boundaries_and_quantization(self):
        rows = []
        for i in range(1, 49):
            for kind, dt in ((1, 0), (9, 10), (23, 30), (2, 40)):
                rows.append(
                    SimpleNamespace(
                        kind=kind,
                        ns=i * 50 + dt,
                        call=i,
                        tile=1,
                        layer=0,
                        wave=0,
                        a={1: 5, 2: 148}.get(i, 1) if kind == 1 else 0,
                    )
                )
        client = dict(timings=dict(predicted_ms=0.008, prompt_ms=10, predicted_n=47))
        summary = dict(decode_s=0.000008, prefill_s=0.01, completion_n=47, predicted_n=47)
        _, c = m.clock(rows, client, summary)
        self.assertEqual(
            (c["decode_callbacks"], c["decode_remap_union_ns"], c["fixed_decode_ns"]),
            (46, 920, 6080),
        )
        rows[-2].ns += 11
        with self.assertRaisesRegex(ValueError, "callback"):
            m.clock(rows, client, summary)


if __name__ == "__main__":
    unittest.main()
