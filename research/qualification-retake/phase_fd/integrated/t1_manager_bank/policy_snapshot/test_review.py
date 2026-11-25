import json
import os
import struct
import unittest
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

r = run_path(Path(__file__).with_name("review.py"))
fd = run_path(r["PFJ_SOURCE"])
ARMS = r["ARMS"]


def fixture(mode):
    rows = []

    def add(kind, **kw):
        fields = dict.fromkeys(fd["Row"]._fields, 0)
        fields.update(ns=len(rows) + 1, kind=kind, call=1)
        fields.update(kw)
        rows.append(fd["Row"](**fields))

    pending = mode == "pending"
    add(1, a=1 if mode == "missing" else 5, b=2044, c=2044 if mode == "missing" else 2048)
    add(7, fd=3, a=100, b=12, c=os.O_DIRECT)
    for layer in range(36):
        for s in range(40):
            load = pending and layer == 0 and s in (1, 2)
            add(5, layer=layer, slot=s, expert=s, gen=1, a=1 if load else 2, b=int(load and s == 2))
        for k in range(3):
            add(8, fd=3, layer=layer, component=k, a=4096 * k, b=32)
    if pending:
        for i in range(2):
            add(6, slot=1, expert=1, gen=1, a=i, b=1)
    add(2, b=2 if pending else 0, c=int(pending))
    if pending:
        for s in (1, 2):
            add(26, slot=s, expert=s, gen=1, a=1, b=int(s == 2))
        for i in range(2):
            add(6, slot=1, expert=1, gen=1, a=i, b=2)
    if mode == "duplicate":
        add(1, call=2, a=5, b=2044, c=2048)
        add(2, call=2)
    add(25, call=0)
    head = fd["HEADER"].pack(b"TESYPF1\0", 1, 96, 262144, len(rows), len(rows), 1, 0)
    journal = head + b"".join(fd["RECORD"].pack(*row) for row in rows)
    state = {"pending": 2, "duplicate": 3, "missing": 0}.get(mode, 1)
    hdr = (
        (0,) * 15
        if state == 0
        else (
            state,
            2 if mode == "duplicate" else 1,
            1,
            5,
            2044,
            2048,
            2303,
            2304,
            4,
            36,
            40,
            128,
            *((2, 1, 2) if pending else (0, 0, 0)),
        )
    )
    side = struct.pack("<8s15q", b"TPOLICY1", *hdr)
    if state == 1:
        for layer in range(36):
            freq = [20] * 128
            freq[:3] = [0, 5, 7]
            if layer == 0 and mode in ("heat-b", "age-a", "age-b"):
                freq[1] = 9 if mode == "heat-b" else 7
            ages = list(range(1, 41))
            if layer == 0 and mode == "age-b":
                ages[1:3] = [3, 2]
            side += struct.pack("<169q", 40, *ages, *freq)
    return (
        journal,
        side,
        {"r0": 0, "backed": 0 if pending else 2 if mode in ("heat-b", "age-b") else 1},
    )


class Review(unittest.TestCase):
    def test_eight_arms_and_false_choice(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            for mode in ARMS:
                jf, side, native = fixture(mode)
                loc = root / mode
                loc.mkdir()
                (loc / "journal.pfj").write_bytes(jf)
                (loc / "native.json").write_text(json.dumps(native))
                if mode != "off":
                    (loc / "policy.bin").write_bytes(side)
            result = r["family"](root)
            self.assertEqual(
                [p["differing_policy_words"] for p in result["pairs"].values()], [1, 2]
            )
            p = root / "age-b" / "native.json"
            p.write_text('{"r0":0,"backed":1}')
            with self.assertRaisesRegex(ValueError, "native victim"):
                r["family"](root)

    def test_corrupt_words_negatives_and_trailing_bytes(self):
        _, raw, _ = fixture("heat-a")
        enters = [(1, 5, 2044, 2048)]
        for offset in (128 + 8 * 7, len(raw) - 8):
            changed = bytearray(raw)
            changed[offset] ^= 1
            with self.assertRaisesRegex(ValueError, "counter/age/hotness"):
                r["grade_policy"]("heat-a", changed, enters)
        _, pending, _ = fixture("pending")
        for bad in (raw[:128], pending + raw[128:], pending[:-1]):
            with self.assertRaises(ValueError):
                r["grade_policy"]("pending", bad, enters)
        with self.assertRaisesRegex(ValueError, "match classification"):
            r["grade_policy"]("pending", pending, enters + [(2, 5, 2044, 2048)])

    def test_skip_loaded_even_when_recoverable(self):
        slots = [(i, 2, 0) for i in range(40)]
        slots[1] = (1, 1, 0)
        slots[2] = (2, 1, 1)
        self.assertEqual(
            r["predicted"](r["population"]("pending", 0), slots), {"r0": 0, "backed": 0}
        )


if __name__ == "__main__":
    unittest.main()
