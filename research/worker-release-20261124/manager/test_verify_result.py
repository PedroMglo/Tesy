import copy
import gzip
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "manager_verification", Path(__file__).with_name("verify_result.py")
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def make_events():
    events = []

    def emit(kind, w=-1, e=-1, k=-1, ticket=0, slot=-1, tid=72):
        s = len(events) + 1
        events.append(
            dict(
                seq=s,
                ns=s * 1000,
                worker=w,
                tid=100 + w if w >= 0 else tid,
                kind=kind,
                expert=e,
                slot=slot,
                generation=int(slot >= 0),
                ticket=ticket,
                component=k,
            )
        )

    def stage(phase, e, k=-1):
        emit(phase, e - 1, e, k, e + 10)

    def primary(kind, e, k=-1):
        emit(
            kind,
            3 if e == 1 else 1,
            e,
            k,
            11 if kind in ("park", "resume", "claim") else 0,
            4 if e == 1 else 5,
        )

    for w in range(4):
        emit("worker_enter", w)
    for e in (2, 3, 1):
        stage("stage_start", e)
        stage("stage_read_begin", e, 0)
    emit("barrier_begin")
    primary("primary_accept", 1)
    primary("park", 1)

    def release(e):
        stage("stage_read_end", e, 0)
        for k in (1, 2):
            stage("stage_read_begin", e, k)
            stage("stage_read_end", e, k)
        stage("stage_complete", e)

    release(2)
    primary("primary_accept", 4)
    primary("direct_read_begin", 4, 0)
    release(1)
    primary("resume", 1)
    primary("claim", 1)
    for k in range(3):
        primary("copy_begin", 1, k)
        primary("copy_end", 1, k)
    primary("primary_publish", 1)
    for k in range(3):
        if k:
            primary("direct_read_begin", 4, k)
        primary("direct_read_end", 4, k)
        primary("copy_begin", 4, k)
        primary("copy_end", 4, k)
    primary("primary_publish", 4)
    emit("barrier_end")
    emit("remap_return")
    emit("finish_begin", tid=75)
    release(3)
    emit("finish_end", tid=75)
    emit("shutdown", tid=71)
    for w in reversed(range(4)):
        emit("worker_exit", w)
    return events


class ManagerVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.rows = []
        for expert, slot in [(1, 4), (4, 5), (8, 0), (9, 1)]:
            files = []
            for k in range(3):
                fname = f"dest-{slot}-{k}.bin.gz"
                # Independently generate fixture bytes in blocks across period boundaries.
                block = bytes(
                    (29 * expert + 61 * k + 11 * (i % 251)) & 255 for i in range(251 * 67)
                )
                n, last = divmod(4_406_400, len(block))
                with gzip.open(cls.root / fname, "wb", compresslevel=1) as stream:
                    for _ in range(n):
                        stream.write(block)
                    stream.write(block[:last])
                files.append(fname)
            cls.rows.append(dict(expert=expert, slot=slot, generation=1, files=files))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.r = dict(
            counters=dict(verifier.COUNTERS),
            terminal=dict(verifier.TERMINAL),
            destinations=copy.deepcopy(self.rows),
            events=make_events(),
        )

    def event(self, name, expert=-1):
        return next(e for e in self.r["events"] if e["kind"] == name and e["expert"] == expert)

    def test_scheduled_on_off_pair_same_destinations(self):
        r = verifier.verify(self.r, True, self.root)
        self.assertEqual(r["worker_count_observed"], 4)
        self.assertEqual(r["events"], 63)
        self.r["events"] = []
        self.assertEqual(
            verifier.verify(self.r, False, self.root)["destinations_sha256"],
            r["destinations_sha256"],
        )

    def test_missing_or_duplicate_event(self):
        rows = self.r["events"]
        index = rows.index(self.event("stage_complete", 3))
        rows[index] = rows[index - 1] | dict(seq=index + 1, ns=rows[index]["ns"])
        with self.assertRaisesRegex(ValueError, "duplicate event"):
            verifier.verify(self.r, True, self.root)

    def test_publication_order_cannot_be_fabricated_by_counts(self):
        a = self.event("primary_publish", 4)
        b = self.event("barrier_end")
        first, second = a.copy(), b.copy()
        a.update(second, seq=first["seq"], ns=first["ns"])
        b.update(first, seq=second["seq"], ns=second["ns"])
        with self.assertRaisesRegex(ValueError, "causal order"):
            verifier.verify(self.r, True, self.root)

    def test_ticket_and_generation(self):
        self.event("resume", 1)["ticket"] += 1
        with self.assertRaisesRegex(ValueError, "ticket"):
            verifier.verify(self.r, True, self.root)
        self.r["events"] = make_events()
        self.event("copy_end", 4)["generation"] = 2
        with self.assertRaisesRegex(ValueError, "generation"):
            verifier.verify(self.r, True, self.root)

    def test_reject_wrong_native_thread_for_direct_dispatch(self):
        r = self.event("primary_accept", 4)
        r.update(worker=2, tid=102)
        with self.assertRaisesRegex(ValueError, "worker"):
            verifier.verify(self.r, True, self.root)

    def test_missing_or_unordered_drain(self):
        self.r["events"].pop(-6)  # remove finish_end
        for i, r in enumerate(self.r["events"], 1):
            r["seq"] = i
        with self.assertRaisesRegex(ValueError, "missing"):
            verifier.verify(self.r, True, self.root)

    def test_off_must_be_empty_and_terminal_strict(self):
        with self.assertRaisesRegex(ValueError, "OFF"):
            verifier.verify(self.r, False, self.root)
        self.r["terminal"]["claimed"] = True
        with self.assertRaisesRegex(ValueError, "claimed"):
            verifier.verify(self.r, True, self.root)

    def test_swapping_components_and_slot_order(self):
        fs = self.r["destinations"][0]["files"]
        fs[0], fs[1] = fs[1], fs[0]
        with self.assertRaisesRegex(ValueError, "wrong bytes"):
            verifier.verify(self.r, True, self.root)
        self.r["destinations"].reverse()
        with self.assertRaisesRegex(ValueError, "expert"):
            verifier.verify(self.r, True, self.root)

    def test_short_oversize_and_corrupted_gzip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fault.bin.gz"
            for size, label in [(verifier.SLAB - 1, "short"), (verifier.SLAB + 1, "oversize")]:
                p.write_bytes(gzip.compress(bytes(size), compresslevel=1))
                with self.assertRaisesRegex(ValueError, label):
                    verifier.read_slab(p)
            p.write_bytes(gzip.compress(bytes(verifier.SLAB), compresslevel=1)[:-8])
            with self.assertRaisesRegex(ValueError, "corrupt"):
                verifier.read_slab(p)


if __name__ == "__main__":
    unittest.main()
