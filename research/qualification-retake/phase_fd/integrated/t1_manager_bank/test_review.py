import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review  # noqa: E402


class ReviewTest(unittest.TestCase):
    def slots(self, mode):
        rows = []
        roles = [[str(i)] * 3 for i in range(6)]
        for i in range(40):
            e = i + 40 if i < 4 else (39, 36, 38, 37)[i - 4] if i < 8 else i - 4
            new = mode == "stale" and i == 4
            failed = new or (mode == "eio" and i == 5)
            row = dict(
                slot=i, expert=e, generation=1 + (i < 8) + new, claimed=new, resident=not failed
            )
            if not failed:
                row["role_sha256"] = roles[0 if e < 36 else min(5, e - 35)]
            rows.append(row)
        return rows, roles

    def test_reject_old_completion_and_false_new_release(self):
        rows, roles = self.slots("stale")
        self.assertEqual(review.verify_slots("stale", rows, roles), [[4, 39, 3, True]])
        for field, value in (("generation", 2), ("claimed", False), ("resident", True)):
            changed = copy.deepcopy(rows)
            changed[4][field] = value
            with self.assertRaises(ValueError):
                review.verify_slots("stale", changed, roles)

    def test_eio_cannot_publish_or_claim_content(self):
        rows, roles = self.slots("eio")
        self.assertEqual(review.verify_slots("eio", rows, roles), [[5, 36, 2, False]])
        rows[5]["role_sha256"] = roles[1]
        with self.assertRaises(ValueError):
            review.verify_slots("eio", rows, roles)

    def test_gate_down_up_order(self):
        rows, roles = self.slots("on")
        roles[1] = ["gate", "down", "up"]
        rows[5]["role_sha256"] = ["gate", "up", "down"]
        with self.assertRaises(ValueError):
            review.verify_slots("on", rows, roles)

    def test_eio_request_is_not_returned(self):
        w = review.WINDOW
        row = {
            "offset_alignment": 4096,
            "read_extent": w,
            "claims": [40, 4, 4],
            "preads": [40, 4, 1],
            "requested_bytes": [40 * w, 4 * w, w],
            "returned_bytes": [40 * w, 4 * w, 0],
            "sets": [120, 12, 9],
            "bank_hits_T2": 3,
            "bank_payload_captured_T1": 4 * review.PAYLOAD,
            "peak_bank_payload_bytes": 3 * review.PAYLOAD,
            "manager_store_reads_committed": 44,
            "pack_proof_bytes": 2 * review.PACK,
        }
        self.assertEqual(review.verify_work("eio", row)["returned_bytes"][2], 0)
        row["returned_bytes"][-1] = w
        with self.assertRaises(ValueError):
            review.verify_work("eio", row)


if __name__ == "__main__":
    unittest.main()
