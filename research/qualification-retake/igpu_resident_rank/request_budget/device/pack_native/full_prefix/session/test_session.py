import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import family

c = family.local


class SealTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.journal = self.out / "journal"

    def test_empty_native_header(self):
        with self.journal.open("xb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(struct.pack("<8s7Q", b"TESYFP1\0", 1, 96, c.CAPACITY, 0, 0, 0, 0))
            f.truncate(c.BYTES)
        c.initial_journal(self.journal)
        with self.journal.open("r+b") as f:
            f.seek(64)
            f.write(b"x")
        with self.assertRaises(ValueError):
            c.initial_journal(self.journal)
        self.journal.chmod(0o644)
        with self.assertRaises(ValueError):
            c.initial_journal(self.journal)

    def test_selection_before_post_and_pins(self):
        rows = ["only T1"]
        proof = {
            "prefill_calls": list(range(1, 10)),
            "records": 91,
            "sha256": "8" * 64,
            "bytes": 91 * 96,
        }

        def select(observed, calls, capacity):
            self.assertIs(observed, rows)
            self.assertEqual(calls, proof["prefill_calls"])
            self.assertEqual(capacity, 353)
            return {
                "policy_sha256": c.POLICY,
                "prefill_calls": calls,
                "capacity": capacity,
                "banks": {name: {"held": 0, "ordered_keys": []} for name in ("lru", "prefill")},
            }

        seal, sha, done = c.record_seal(
            self.out, self.journal, lambda p: (rows, proof), select, iter((3, 6, 8)).__next__
        )
        self.assertEqual(c.pinned(self.out / "before-t2.json", sha), seal)
        self.assertEqual(done, 8)
        with self.assertRaises(FileExistsError):
            c.record_seal(self.out, self.journal, lambda p: (rows, proof), select)
        with self.assertRaises(ValueError):
            c.record_seal(
                self.out,
                self.journal,
                lambda p: (rows, proof | {"records": c.CAPACITY - 262144 + 1}),
                select,
            )

    def test_no_post_on_invalid_cut(self):
        q = c.Runtime.__new__(c.Runtime)
        q.obs = self.out / "observer"
        q.journal = q.obs / "events.pfj"
        q.trigger = q.obs / "T1.trigger"
        q.out = self.out
        q.turn = 1
        q.label = "ON"
        q.jfds = [{}]
        q.reference = {"historical_inputs": ["a", "b"]}
        q.trigger_ns = 17
        q.seal_sha = q.seal_end_ns = None
        q.posts_ns = [18]
        q.stats = {"pack": {}, "model": {}}
        q.audit = {"seal_before_post": lambda *args: None}
        q.selector = None

        def bad(*a, **kw):
            raise ValueError("unpublished cut")

        with (
            patch.object(c.p.session.client, "stream_chat") as real,
            patch.object(c, "pre_second"),
            patch.object(c, "record_seal", bad),
        ):
            with q.posts():
                q.trigger.touch()
                with self.assertRaisesRegex(ValueError, "unpublished cut"):
                    c.p.session.client.stream_chat()
            real.assert_not_called()
            self.assertIs(c.p.session.client.stream_chat, real)

    def test_expired_seal(self):
        meta = {"prefill_calls": list(range(1, 10)), "records": 100, "sha256": "0" * 64}
        banks = {key: {"held": 0, "ordered_keys": []} for key in ("lru", "prefill")}

        def select(rows, calls, capacity):
            return dict(policy_sha256=c.POLICY, prefill_calls=calls, capacity=capacity, banks=banks)

        with self.assertRaisesRegex(ValueError, "deadline"):
            c.record_seal(
                self.out,
                self.journal,
                lambda f: ([], meta),
                select,
                iter((0, 7, 15_000_000_001)).__next__,
            )

    def test_disk_grade_is_same_object(self):
        args = SimpleNamespace(unit_prefix="test", arm="OFF", execute=True)
        result = {"full_prefix": {"label": "OFF"}}

        def grade(out, receipt, *unused):
            self.assertEqual(c.pinned(out / "receipt.json", c.sha(out / "receipt.json")), receipt)
            self.assertEqual(receipt["pack_events"]["label"], "OFF")
            return {"rows": [], "trajectories": [1, 2], "requests": 2, "model_launches": 1}

        with (
            patch.object(c, "invoke", return_value=result),
            patch.object(family, "historical", return_value={"grade": {"trajectories": [1, 2]}}),
            patch.dict(family.prior, {"graded": grade}),
        ):
            self.assertEqual(family.single(args, self.out)["status"], "PASS_ONE_NATURAL_ARM")


if __name__ == "__main__":
    unittest.main()
