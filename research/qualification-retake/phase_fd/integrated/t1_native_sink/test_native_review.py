"""Model-free fault and conservation checks for the native transfer review."""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

review = run_path(str(Path(__file__).with_name("review.py")))
WIDTH, WINDOW, SLAB = (review[k] for k in ("WIDTH", "WINDOW", "SLAB"))


def fake_plan():
    seal = json.loads((review["RAM"] / "plan-receipt.json").read_bytes())
    entries, samples = [], {}
    for idx, key in enumerate(review["STRATA"]):
        layer = idx + (25 if key.endswith("_cuda") else 0)
        count = seal["sample_counts"][key]
        demand = list(range(count["consumers"]))
        paths = {
            name: [s for s, num in m.items() for _ in range(num)]
            for name, m in count["origins"].items()
        }
        samples[key] = dict(site=[0, 0, layer, 0], demand=demand, paths=paths)
        for expert in demand:
            n = 3 * len(entries)
            gguf = [dict(size=SLAB, count=4_411_392, sha256=f"{n + i:064x}") for i in range(3)]
            entries.append(dict(expert=expert, layer=layer, gguf=gguf))
    return dict(samples=samples, entries=entries, weight_window=WINDOW), seal


class Review(unittest.TestCase):
    def test_sealed_plan_counts_zero_dispatch_and_changed_sources(self):
        plan, seal = fake_plan()
        costs, preparation = review["plan_costs"](plan, seal)
        self.assertEqual(preparation, 29 * WINDOW + 87 * 4_411_392)
        src = costs["A"]["148_cpu"]
        self.assertEqual(
            (src["set_bytes"], src["read_bytes"], src["bank_bytes"]),
            (12 * WIDTH, 33 * 4_411_392, WIDTH),
        )
        self.assertEqual(costs["D"]["148_cpu"]["fd_calls"], 10)
        self.assertEqual(costs["D"]["decode_cuda"]["set_bytes"], 0)
        self.assertEqual(costs["D"]["decode_cuda"]["verified_components"], 12)
        wrong = deepcopy(plan)
        wrong["samples"]["148_cpu"]["paths"]["lru_ram"][0] = "primary"
        with self.assertRaisesRegex(ValueError, "origins"):
            review["plan_costs"](wrong, seal)
        wrong = deepcopy(plan)
        wrong["entries"][0]["gguf"][2] = wrong["entries"][0]["gguf"][0]
        with self.assertRaisesRegex(ValueError, "87 addressed"):
            review["plan_costs"](wrong, seal)

    def test_rows_reconcile_by_stratum_and_exclude_warm(self):
        plan, seal = fake_plan()
        costs, prep = review["plan_costs"](plan, seal)
        rows, blocks = [], []
        for n, seq in enumerate(review["ORDER"]):
            b = {}
            for cell in seq:
                waves = {}
                for s, e in costs[cell].items():
                    w = {
                        k: e[k]
                        for k in (
                            "tier",
                            "served",
                            "dispatched",
                            "bank_bytes",
                            "read_bytes",
                            "set_bytes",
                            "verified_components",
                        )
                    }
                    w["ns"] = (1000 if n == 0 else 100) - 10 * "ABCD".index(cell)
                    if n == 2 and s == "148_cuda" and cell == "D":
                        w["ns"] += 120
                    waves[s] = w
                b[cell] = waves
                rows.append(dict(cell=cell, block=n, waves=waves))
            blocks.append(b)
        r = dict(
            verified_components=1740,
            arm_read_bytes=sum(w["read_bytes"] for row in rows for w in row["waves"].values()),
            contrasts=review["bench"]["contrast"](blocks[1:]),
        )
        result = review["service"](rows, r, costs, prep)
        self.assertTrue(result["passes"])
        self.assertEqual(result["timing"]["148_cuda"]["effects"]["combined"]["positive"], 3)
        self.assertEqual(result["timing"]["148_cuda"]["effects"]["combined"]["min_block"], 2)
        self.assertEqual(result["warm_ns"]["aggregate"]["A"], 4000)
        self.assertEqual(result["timing"]["aggregate"]["median_ms"]["A"], 400 / 1e6)
        broken = deepcopy(rows)
        broken[0]["waves"]["148_cpu"]["set_bytes"] -= 1
        broken[0]["waves"]["148_cuda"]["set_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "service conservation"):
            review["service"](broken, r, costs, prep)
        with self.assertRaisesRegex(ValueError, "complete paired blocks"):
            review["service"](rows[1:], r, costs, prep)

    def test_changed_raw_hash(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "blocks.jsonl"
            p.write_text('{"block":0}\n')
            digest = review["digest"](p)
            p.write_text('{"block":1}\n')
            with self.assertRaisesRegex(ValueError, "journal hash"):
                review["journal"](p, digest)


if __name__ == "__main__":
    unittest.main()
