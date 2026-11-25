import os
import unittest
from copy import deepcopy
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
r = run_path(HERE / "order_review.py")


class CrossTests(unittest.TestCase):
    def test_zero_and_opposite_signs_follow_frozen_decision(self):
        cases = (
            (0, 0, "NO_POSITIVE_BENEFIT_IN_EITHER_BLOCK"),
            (-1, -2, "NO_POSITIVE_BENEFIT_IN_EITHER_BLOCK"),
            (1, 0, "BLOCK_DEPENDENT_OR_TIE"),
            (-1, 2, "BLOCK_DEPENDENT_OR_TIE"),
            (1, 2, "BENEFIT_IN_BOTH_ORDERS"),
        )
        for a, b, expected in cases:
            self.assertEqual(r["classify"](a, b), expected)
        with self.assertRaises(ValueError):
            r["classify"](float("nan"), 2)

    def test_bind_counterexamples_and_physical_sequence(self):
        p = dict(mode="P", clean_ns=100_000_000_000, pid=111)
        o = dict(mode="O", spawn_ns=170_000_000_000, pid=222, c118_s=60)
        witness = dict(
            previous="P",
            pid=111,
            port=18442,
            limit_s=75,
            bind_available=True,
            elapsed_s=8,
            samples=[dict(elapsed_s=1, tcp_states={"06": 2}), dict(elapsed_s=7, tcp_states={})],
        )
        self.assertEqual(r["verify_wait"](witness, p, o, 8)["closed_to_popen_s"], 70)
        for w, n in (
            (witness | {"previous": "R"}, o),
            (witness | {"bind_available": False}, o),
            (witness | {"samples": [dict(elapsed_s=4, tcp_states={"0A": 1})]}, o),
            (witness, o | {"spawn_ns": 160_000_000_000}),
        ):
            with self.assertRaises(ValueError):
                r["verify_wait"](w, p, n, 8)

    def test_spread_not_pooled_and_work_remains_identified(self):
        dif = {
            k: {"seconds_saved": v}
            for k, v in zip(r["legacy"]["TIMES"], (-1, 2, 3, 4, 5), strict=True)
        }
        dif["decode_tok_s_delta"] = 0.4
        a = dict(
            order="ROP",
            gpu_driver_and_work_sha256="shared",
            libllama_sha256={"P": "common"},
            differences={
                k: {t: deepcopy(dif) for t in ("T1", "T2")} for k in ("R_O", "O_P", "R_P")
            },
        )
        b = deepcopy(a)
        b["order"] = "POR"
        b["differences"]["O_P"]["T2"]["first_final_s"]["seconds_saved"] = 2
        graded = r["compare_blocks"](a, b)
        self.assertEqual(
            graded["by_contrast"]["O_P"]["T2"]["first_final_s"], {"ROP": -1, "POR": 2, "span": 3}
        )
        self.assertEqual(graded["t2_first_final_pack_effect"], "BLOCK_DEPENDENT_OR_TIE")
        with self.assertRaisesRegex(ValueError, "cross-block work"):
            r["compare_blocks"](a, b | {"gpu_driver_and_work_sha256": "different"})

    @unittest.skipUnless(
        os.getenv("TESY_ORDER_ROP") and os.getenv("TESY_REVIEW_HISTORY"), "optional sealed R02"
    )
    def test_historical_block_and_legacy_receipt(self):
        root = Path(os.environ["TESY_ORDER_ROP"])
        history = Path(os.environ["TESY_REVIEW_HISTORY"])
        original = r["legacy"]["extract"](root, history)
        self.assertEqual(original, r["read"](HERE / "evidence/rop-r02.json"))
        review = r["block"](root, "ROP", r["ROP_SHA"], history)
        self.assertEqual([x["previous"] for x in review["transitions"]], ["R", "O"])
        with self.assertRaisesRegex(ValueError, "sealed family"):
            r["block"](root, "ROP", "0" * 64, history)


if __name__ == "__main__":
    unittest.main()
