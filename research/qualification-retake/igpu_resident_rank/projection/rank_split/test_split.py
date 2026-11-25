import copy
import hashlib
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
mod = run_path(HERE / "grade.py")
grade = mod["grade"]


def make_fixture():
    ranks = b"".join(bytes([i]) * 11520 for i in range(4))
    ffn = b"x" * 11520

    def obs(x):
        return {"sha256": hashlib.sha256(x).hexdigest(), "nonfinite": 0, "unequal": 0}

    obs0 = {
        "weighted": [obs(ranks[i : i + 11520]) for i in range(0, len(ranks), 11520)],
        "ffn": obs(ffn),
    }
    fault = copy.deepcopy(obs0)
    fault["weighted"][0] = dict(fault["weighted"][1], unequal=2880)
    fault["ffn"] = dict(obs(b"y" * 11520), unequal=2880)
    r = dict(
        status="PASS_RESIDENT_RANK_SPLIT_EXACT_TIMINGS",
        order=[28, 24, 8, 16],
        physical=[3, 14, 6, 35],
        generations=[6, 6, 5, 4],
        threads=8,
        parity={m: copy.deepcopy(obs0) for m in mod["NAMES"]},
        negative=fault,
        weighted_sha256=obs(ranks)["sha256"],
        ffn_sha256=obs(ffn)["sha256"],
        timings=[],
    )
    ns = 100
    for block in range(2):
        for rep in range(7):
            for mode in mod["NAMES"] if not block else reversed(mod["NAMES"]):
                end = (
                    ns
                    + {
                        "Full": 5000000,
                        "Serial": 6000000,
                        "Free": 3000000 if not block else 4300000,
                    }[mode]
                )
                r["timings"].append(dict(block=block, rep=rep, mode=mode, start_ns=ns, end_ns=end))
                ns = end + 5
    return r, ranks, ffn


class SplitTests(unittest.TestCase):
    def test_negative_pair_order_and_bounds(self):
        r, w, f = make_fixture()
        g = grade(r, w, f)
        self.assertEqual(g["contrasts"]["Free"]["thresholds"]["six_low"], "BLOCK_DEPENDENT")
        self.assertEqual(g["contrasts"]["Serial"]["median_ns"], -1000000)
        self.assertEqual(
            g["contrasts"]["Free"]["thresholds"]["first_final_low"], "NEITHER_BLOCK_MEDIAN_REACHES"
        )
        r["timings"][0]["mode"] = "Serial"
        with self.assertRaises(ValueError):
            grade(r, w, f)

    def test_parity_mismatch_stops_timing(self):
        r, w, f = make_fixture()
        r["status"] = "NO_GO_CROSS_SHAPE_EXACTNESS"
        row = r["parity"]["Serial"]["weighted"][0]
        row.update(unequal=1, sha256="a" * 64)
        with self.assertRaises(ValueError):
            grade(r, w, f)
        del r["timings"]
        self.assertEqual(grade(r, w, f)["timed_graphs"], 0)

    def test_original_materialization(self):
        recipe = run_path(HERE / "build.py")
        original = (recipe["parent"].DECODE / "decode.cpp").read_text()
        transformed = recipe["materialize"](original)
        lines = transformed.splitlines()
        new = [s for s in lines if "run_split(cpu.get()," in s or s == '#include "engine.inc"']
        self.assertEqual(len(new), 2)
        self.assertEqual([s for s in lines if s not in new], original.splitlines())
        with self.assertRaises(ValueError):
            recipe["materialize"](original + original)


if __name__ == "__main__":
    unittest.main()
