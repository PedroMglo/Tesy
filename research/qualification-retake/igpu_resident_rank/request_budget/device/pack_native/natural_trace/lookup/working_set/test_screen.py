import hashlib
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

R = run_path(str(Path(__file__).with_name("screen.py")))
Row = R["NATURAL"]["PFJ"]["Row"]


def row(kind, call, **kw):
    return Row(**(dict.fromkeys(Row._fields, 0) | {"kind": kind, "call": call} | kw))


def trajectory():
    return (
        ["prefill"] * 2 + ["ar"] * 23 + ["anchor"] * 4 + ["anchor", "skip", "skip"] * 6 + ["anchor"]
    )


class Bounds(unittest.TestCase):
    def test_joint_counts_restore_only_once(self):
        start = {(0, 1), (25, 1)}
        known = {(0, 1), (0, 7), (25, 7)}
        final = {(0, 1), (0, 7), (25, 5)}
        m = R["bundle"]([R["measure_sets"](start, final, known)])
        self.assertEqual([m[k]["jobs"] for k in R["FIELDS"]], [2, 2, 1, 3])
        self.assertEqual(m["joint"]["by_tier"], {"cpu": 1, "cuda": 2})
        self.assertEqual(m["joint"]["payload_bytes"], 3 * 13_219_200)
        self.assertEqual(m["joint"]["requested_bytes"], 3 * 13_221_888)

    def test_prefix_and_free_rejected_rows(self):
        g = R["blocks"](trajectory())
        before = {i: ("source", set(), False) for i in range(3, 49)}
        after = {i: ("final", {(0, 127)}, False) for i in range(3, 49)}
        ranks = {i: [(0, i)] for i in range(3, 49)}
        # One accepted block shares its first and second row's expert.
        ranks[31] = ranks[30]
        blocks, totals = R["sets_at_cuts"](g, before, after, ranks, defaultdict(Counter), 46)
        self.assertEqual(len(blocks), 11)
        reject = blocks[0]
        self.assertEqual(reject["known_input_rows"], 1)
        self.assertEqual(reject["off_trajectory_rows_unpriced"], 2)
        self.assertEqual(reject["acquisition_floor"]["joint"]["jobs"], 2)
        last = next(item for item in blocks if "partial_cut" in item)
        self.assertEqual(last["calls"], [45, 47])
        self.assertEqual(last["partial_cut"]["early_delivery"]["joint"]["jobs"], 2)
        self.assertEqual(last["partial_cut"]["all_inputs_before_delivery"]["joint"]["jobs"], 3)
        self.assertEqual(last["acquisition_floor"]["joint"]["jobs"], 4)
        self.assertEqual(
            totals["first_final_atomic"]["joint"]["jobs"] - totals["first_final"]["joint"]["jobs"],
            1,
        )
        self.assertEqual(
            totals["decode"]["joint"]["jobs"] - totals["first_final"]["joint"]["jobs"], 4
        )

    def test_slot_lineage_and_drain(self):
        slots = {(layer, s): (-1, 0, 0) for layer in range(36) for s in range(40)}
        init = [row(5, 1, layer=layer, slot=s, expert=-1) for layer, s in slots]
        events = init + [
            row(1, 1),
            row(2, 1),
            row(1, 2),
            row(11, 2, expert=7, a=-1, gen=1),
            row(17, 2, expert=7, gen=1),
            row(2, 2),
            row(1, 3),
        ]
        events.extend(row(27, 3, layer=layer, a=0x04030201) for layer in range(36))
        events.append(row(2, 3))
        slots[0, 0] = (7, 1, 2)
        seal = R["footprint"](slots)[0]
        z = R["census"](events, seal, 3)
        self.assertEqual(z[1][2][0], z[0][3][0])
        self.assertEqual(z[2:4], (set(), set()))
        broken = [e._replace(b=1) if e.kind == 2 and e.call == 2 else e for e in events]
        self.assertEqual(R["census"](broken, seal, 3)[2], {2})
        broken = [e._replace(gen=2) if e.kind == 17 else e for e in events]
        with self.assertRaisesRegex(ValueError, "publication"):
            R["census"](broken, seal, 3)
        with self.assertRaisesRegex(ValueError, "primary identity"):
            R["census"](events, hashlib.sha256(b"wrong").hexdigest(), 3)

    def test_remap_bytes_not_charged_again(self):
        totals = R["bundle"]([R["measure_sets"](set(), {(0, 1)}, {(0, 1)})])
        ns = totals["joint"]["payload_bytes"] // 8
        budget = {
            "anchors_to_charge": 10,
            "fractions": {"100": {"budget_for_all_verification_and_overheads_ns": ns - 1}},
        }
        p = R["price"](totals, {"fixed_outside": budget}, 10)
        row = p["joint/payload_bytes/8000000000_Bps"]["net"]["fixed_outside"]["100"]
        self.assertEqual(row["total_remaining_ns"], -1)
        self.assertEqual(row["status"], "NO_GO_FIXED_SCENARIO")
        with self.assertRaisesRegex(ValueError, "verify count"):
            R["price"](totals, {"x": budget}, 11)


if __name__ == "__main__":
    unittest.main()
