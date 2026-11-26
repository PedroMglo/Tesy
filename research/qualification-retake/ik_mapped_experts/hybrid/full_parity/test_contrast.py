import struct
import unittest
from pathlib import Path
from runpy import run_path

MOD = run_path(str(Path(__file__).with_name("contrast.py")))


def records(offset=0):
    output = []
    for phase in ("prefill", "teacher"):
        for layer in range(36):
            width = 16 if phase == "prefill" and layer < 35 else 1
            ids = list(range(4))
            slots = [4 * layer + e + offset for e in ids]
            output.append(
                dict(
                    phase=phase,
                    layer=layer,
                    logical=ids * width,
                    physical=slots * width,
                    fills=list(zip(ids, slots, strict=True)) if phase == "prefill" else [],
                )
            )
    return output


class NumericalTest(unittest.TestCase):
    def test_rows_signed_zero_ties_nonfinite(self):
        row = struct.pack("<5f", 0, 1, 3, 0, 2)
        out = MOD["cut"](row, struct.pack("<5f", -0.0, 1, 3, 0, 2), 5)
        self.assertEqual(
            (out["changed_words"], out["first_changed_index"], out["rmse"]), (1, 0, 0.0)
        )
        self.assertTrue(out["unique_greedy_equal"])
        tie = MOD["cut"](row, struct.pack("<5f", 3, 1, 3, 0, 2), 5)
        self.assertFalse(tie["unique_greedy_equal"])
        bad = MOD["cut"](row, struct.pack("<5f", float("nan"), 1, 3, 0, 2), 5)
        self.assertIsNone(bad["mean_abs"])
        self.assertEqual(bad["candidate"]["nonfinite"], 1)
        with self.assertRaises(ValueError):
            MOD["cut"](row, row[:-1], 5)

    def test_shared_identity_and_geometry(self):
        a, b = records(1), records()
        places = MOD["compare_placements"](a, b)
        self.assertEqual(
            (
                places["quartets"],
                places["different_slots_at_same_rank"],
                places["different_hit_fill_at_common_site_keys"],
            ),
            (597, 2388, 0),
        )
        x = struct.pack("<5f", 1, 2, 3, 4, 0)
        same = MOD["cut"](x, x, 5)
        rows = {15: same, 16: same}
        decision = MOD["numeric_decision"]
        self.assertEqual(decision(rows, places, (3, 3)), "PASS_PAIRED_NUMERIC_COMPONENT")
        self.assertEqual(
            decision(rows, MOD["compare_placements"](a, a), (3, 3)),
            "INCONCLUSIVE_NO_PLACEMENT_OR_SERVICE_CONTRAST",
        )
        b[-1]["logical"][:2] = b[-1]["logical"][:2][::-1]
        b[-1]["physical"][:2] = b[-1]["physical"][:2][::-1]
        other = MOD["compare_placements"](a, b)
        self.assertEqual(
            other["first_route_difference"], dict(phase="teacher", layer=35, position=16, rank=0)
        )
        self.assertEqual(decision(rows, other, (3, 3)), "NO_GO_BANK_SIZE_PARITY")
        self.assertEqual(decision(rows, places, (3, 0)), "FAIL_FINITE_OR_GREEDY")

    def test_missing_service_and_wrong_pruning(self):
        for mutation in (
            "wrong-layer",
            "missing-site",
            "last-prefill",
            "unproved-hit",
            "duplicate-fill",
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                data = records()
                if mutation == "wrong-layer":
                    data[1]["physical"] = data[0]["physical"]
                    data[1]["fills"] = []
                elif mutation == "missing-site":
                    data.pop()
                elif mutation == "last-prefill":
                    data[35]["logical"] *= 16
                    data[35]["physical"] *= 16
                elif mutation == "unproved-hit":
                    data[0]["fills"].pop()
                else:
                    data[0]["fills"] += data[0]["fills"][:1]
                MOD["bank_sites"](data, 161)


if __name__ == "__main__":
    unittest.main()
