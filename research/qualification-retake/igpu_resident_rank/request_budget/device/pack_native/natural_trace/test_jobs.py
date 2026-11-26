"""Conservation, late service after RETURN, inherited prefixes and maliciously changed records."""

import json
import os
import unittest
from pathlib import Path
from runpy import run_path

CHECK = run_path(Path(__file__).with_name("jobs.py"))
PRIOR = CHECK["PRIOR"]
Row = PRIOR["pfj"]["Row"]
S = CHECK["SLAB"]
W = CHECK["WINDOW"]
PACK = {"dev": 3, "ino": 5678}
GGUF = {"dev": 3, "inode": 8765}


def records(inherited=False):
    rows = []

    def emit(kind, **kw):
        fields = dict.fromkeys(Row._fields, 0)
        fields.update(
            ns=10 * (len(rows) + 1),
            kind=kind,
            layer=0,
            slot=3,
            gen=1,
            expert=0,
            call=1,
            tile=1,
            wave=-1,
            worker=-1,
            fd=-1,
            component=-1,
        )
        rows.append(Row(**(fields | kw)))

    emit(1, a=1, tile=-1)
    emit(7, fd=5, a=3, b=8765, c=os.O_DIRECT)
    emit(29, fd=6, a=3, b=5678, c=os.O_DIRECT)
    for layer in range(36):
        for slot in range(40):
            claim = inherited and layer == 0 and slot == 3
            emit(
                5,
                layer=layer,
                slot=slot,
                a=int(claim),
                b=int(claim),
                gen=int(claim),
                expert=0 if claim else -1,
            )
        for k in range(3):
            emit(8, layer=layer, component=k, b=S, fd=5)
    if inherited:
        emit(3, a=1)
        emit(4)
        emit(2, b=0, c=1)
        emit(26, a=1, b=1)
        emit(16, worker=2, call=0, tile=-1, component=2, fd=6, a=S, b=3 * S, c=2 * S)
        emit(17, worker=2, call=0, tile=-1)
    else:
        emit(3, a=1)
        emit(9, b=4)
        emit(11, a=-1)
        emit(12, a=2)
        emit(12, a=1)
        emit(13, worker=0)
        emit(23)
        emit(4)
        emit(2, b=1, c=1)
        emit(26, a=1, b=1)
        emit(6, a=0, b=2)
        emit(30, begin=rows[-1].ns + 2, worker=0, fd=6, a=0, b=W, c=W)
        for k in range(3):
            emit(16, begin=rows[-1].ns + 2, worker=0, fd=6, component=k, a=S, b=3 * S, c=k * S)
        emit(17, worker=0)
        emit(14, worker=1)
    for i in range(4):
        emit(24, worker=i)
    emit(25)
    return rows


def audit(rows):
    return CHECK["audit_jobs"](rows, PACK, GGUF)


class TestNaturalPacked(unittest.TestCase):
    def test_promotion_returns_late(self):
        r = audit(records())
        self.assertTrue(r["eligible_clean_run"])
        self.assertEqual(r["status"], "COMPLETE")
        n = r["counts"]
        self.assertEqual(
            [n[k] for k in ("enqueues", "promotions", "skipped", "published", "sets", "attempts")],
            [2, 1, 1, 1, 3, 1],
        )
        self.assertEqual(len(r["return_cuts"][0]["queued"]), 1)
        self.assertEqual(r["return_cuts"][0]["claimed"], 1)

    def test_inherited_partial_claim(self):
        r = audit(records(True))
        self.assertFalse(r["eligible_clean_run"])
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(r["by_origin"][0]["call"], 0)
        self.assertEqual((r["counts"]["copied_bytes"], r["counts"]["missing_start"]), (S, 1))
        self.assertEqual(r["counts"]["set_worker_ns"], 0)

    def test_contradictions(self):
        original = records()
        for kind, fields in (
            (29, {"a": 99}),
            (30, {"a": 1}),
            (30, {"b": S}),
            (16, {"component": 2}),
            (17, {"gen": 3}),
            (13, {"slot": 4}),
            (2, {"b": 0}),
            (6, {"a": 1}),
            (26, {"b": 0}),
            (14, {"kind": 13}),
            (25, {"a": 1}),
        ):
            with self.subTest(kind=kind, fields=fields), self.assertRaises(ValueError):
                rows = original[:]
                index = next(i for i, r in enumerate(rows) if r.kind == kind)
                rows[index] = rows[index]._replace(**fields)
                audit(rows)

    @unittest.skipUnless(
        os.environ.get("TESY_PACK_FIXTURE_DIR"), "requires a qualified native fixture"
    )
    def test_previous_physical_fixture(self):
        root = Path(os.environ["TESY_PACK_FIXTURE_DIR"])
        for arm in ("pack-on", "pack-short-on"):
            native = json.loads((root / arm / "native.json").read_bytes())
            f = root / arm / "journal.bin"
            rows, _ = PRIOR["read_journal"](f)
            prior = PRIOR["inspect_journal"](f, packed=True, short="short" in arm)
            r = CHECK["audit_jobs"](rows, native["pack_stat"], native["gguf_stat"])
            self.assertEqual(r["status"], "COMPLETE")
            for k, old in (
                ("sets", "copies"),
                ("attempts", "attempts"),
                ("failed", "failed"),
                ("published", "published"),
                ("read_errors", "__"),
                ("service_worker_ns", "service_worker_ns"),
                ("service_wall_union_ns", "service_wall_union_ns"),
            ):
                self.assertEqual(r["counts"][k], prior.get(old, 0))
            self.assertFalse(r["eligible_clean_run"])


if __name__ == "__main__":
    unittest.main()
