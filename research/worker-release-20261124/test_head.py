"""Synthetic unit tests for FIFO head eligibility, independent of the C317 raw."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from head import blocked_with_head, head_outcomes, run

BLOCKED = (1, 2, 5, 0, 1)
HEAD = (1, 2, 6, 1, 1)


def event(ticket, kind, work):
    return dict(call=work[0], layer=work[1], expert=work[2], scope=1, ticket=ticket, kind=kind)


class HeadEligibility(unittest.TestCase):
    def test_all_head_states_and_later_observed_outcomes(self):
        for before, after, expected, dispatch in [
            ([], [], "ABSENT", "DIRECT"),
            ([1], [4], "QUEUED", "DIRECT"),
            ([1, 2, 5], [3, 4], "ABSENT", "DIRECT"),
            ([1, 2, 3], [6, 7, 11, 8], "READY", "READY"),
            ([1, 2], [3, 6, 7, 11, 8], "READING", "READY"),
            ([1, 2], [6, 3, 7, 11, 8], "READING", "READING"),
        ]:
            with self.subTest(before=before, after=after):
                journal = [event(1, k, BLOCKED) for k in [1, 2]]
                journal += [event(2, k, HEAD) for k in before]
                anchor = len(journal) + 1
                journal += [event(1, k, BLOCKED) for k in [6, 3, 7, 11, 8]]
                journal += [event(2, k, HEAD) for k in after]
                matched = {HEAD: (len(journal) - 3, dispatch == "READING")}
                assignments = matched if dispatch != "DIRECT" else {}
                row = head_outcomes(journal, {anchor: HEAD}, assignments)
                self.assertEqual(row["at_accept_then_at_observed_dispatch"],
                                 {expected: {dispatch: 1}})
                if expected in ("ABSENT", "QUEUED"):
                    with self.assertRaisesRegex(ValueError, "incompatible source"):
                        head_outcomes(journal, {anchor: HEAD}, {HEAD: (99, False)})

    def test_head_tracking_respects_priority_and_capacity(self):
        queue = [SimpleNamespace(kind=k, work=w)
                 for k, w in [(4, BLOCKED), (4, HEAD), (5, BLOCKED), (5, HEAD)]]
        attached = {BLOCKED: (3, True)}
        self.assertEqual(blocked_with_head(queue, [0, 0, 0, 2, 2], [0, 1, 2], attached), {3: HEAD})
        self.assertEqual(blocked_with_head(queue, [0, 0, 0, 1, 2], [0, 1, 2], attached), {})
        queue[2], queue[3] = queue[3], queue[2]
        with self.assertRaisesRegex(ValueError, "FIFO acceptance"):
            blocked_with_head(queue, [0, 0, 0, 2, 2], [0, 1, 2], attached)

    def test_missing_inputs_or_equal_size_hash_mismatch_are_recorded_before_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            spec = {"size_bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
            manifest = {"first": spec, "second": spec}
            (raw / "first").write_bytes(b"abc")
            with (patch("head.source.required_files", return_value=manifest),
                  patch("head.classify") as c):
                self.assertEqual(run(raw, raw / "missing"), 2)
                receipt = json.loads((raw / "missing/head.json").read_text())
                self.assertEqual(receipt["missing"], {"second": spec})
                self.assertEqual(receipt["status"], "NOT_RUN_RAW_REQUIRED")
                (raw / "second").write_bytes(b"abd")
                self.assertEqual(run(raw, raw / "corrupt"), 1)
                receipt = json.loads((raw / "corrupt/head.json").read_text())
                self.assertEqual(receipt["status"], "FAIL")
                self.assertIn("SHA-256 mismatch", receipt["failure"])
                c.assert_not_called()
                with self.assertRaises(FileExistsError):
                    run(raw, raw / "missing")
