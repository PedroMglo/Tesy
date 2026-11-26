"""The sealed workload must preserve slot lineage and reject invalid bindings."""

import copy
import unittest
from pathlib import Path
from runpy import run_path

src = run_path(Path(__file__).with_name("plan.py"))


class TestPlan(unittest.TestCase):
    def test_tiles_and_last_output(self):
        sites = list(src["sites"](74))
        self.assertEqual(len(sites), 1331)
        self.assertEqual(sites[0], ((74, 1, 0, -1), 5))
        self.assertEqual(sites[-1], ((75, 5, 35, -1), 1))
        self.assertEqual({x[:2] for x, _ in sites if x[2] == 35}, {(75, 5)})

    def test_generation_and_order(self):
        ranks = [51, 52, 1, 2]
        s = [(i, 2) for i in range(40)]
        jobs = [(51, 10, 3, 10, 0), (52, 11, 3, 11, 0)]
        src["check_reservations"](ranks, -1, jobs, s.copy())
        for bad in (
            list(reversed(jobs)),
            [(51, 10, 9, 10, 0), jobs[1]],
            [(51, 10, 3, 30, 0), jobs[1]],
            [(53, 10, 3, 10, 0), jobs[1]],
            [jobs[0]],
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                src["check_reservations"](ranks, -1, bad, s.copy())

    def test_source_and_tier(self):
        group = dict(
            call_tokens=5,
            tile=1,
            layer=0,
            tier="CPU",
            jobs=[dict(expert=5, source="bank", source_enqueue=0)],
        )
        for key, value in (("source", "disk"), ("tier", "CUDA0")):
            g = copy.deepcopy(group)
            if key == "tier":
                g[key] = value
            else:
                g["jobs"][0][key] = value
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "source binding|physical tier"),
            ):
                src["counts"]([g], {}, [{5}] + [set() for _ in range(35)])

    def test_corrupt_component(self):
        positions = [(4096 * (i + 1), 4406400) for i in range(3)]
        row = dict(
            expert=0,
            layer=0,
            components=[
                dict(
                    source_offset=b,
                    size_bytes=s,
                    packed_relative_offset=i * s,
                    name="blk.0.ffn_" + role + "_exps.weight",
                    type="mxfp4",
                    sha256="ab" * 32,
                )
                for i, ((b, s), role) in enumerate(
                    zip(positions, src["PRIOR"]["ROLES"], strict=True)
                )
            ],
        )
        self.assertEqual(len(src["PRIOR"]["components"](row, positions)), 3)
        row["components"][1]["source_offset"] += 1
        with self.assertRaises(ValueError):
            src["PRIOR"]["components"](row, positions)


if __name__ == "__main__":
    unittest.main()
