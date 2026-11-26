import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

A = run_path(str(Path(__file__).with_name("audit.py")))
R = A["Row"]


def row(kind, **fields):
    data = dict.fromkeys(R._fields, 0)
    data.update(ns=7, kind=kind, call=1, tile=1, layer=0, worker=-1, wave=-1)
    return R(**(data | fields))


def sample():
    rows = [
        row(1, a=1),
        row(29, fd=4, a=77, b=99, c=os.O_DIRECT),
        row(7, fd=3, a=77, b=98, c=os.O_DIRECT),
    ]
    for layer in range(36):
        rows.extend(
            row(8, layer=layer, component=k, a=k * 4096, b=4_406_400, fd=3) for k in range(3)
        )
        rows.extend(row(5, layer=layer, slot=s, expert=-1) for s in range(40))
    rows.append(row(3, a=1))
    for layer in range(36):
        rows.append(row(27, layer=layer, a=0x03020100))
        if layer == 0:
            rows.extend((row(11, a=-1, expert=0, gen=1), row(17, worker=1, expert=0, gen=1)))
    rows.extend((row(4), row(2)))
    return rows


class Prefix(unittest.TestCase):
    def grade(self, rows):
        return A["prefix_grade"](rows, [1], 1, {"dev": 77, "ino": 99}, {"dev": 77, "ino": 98})[0]

    def test_complete_projection_and_mutations(self):
        rows = sample()
        result = self.grade(rows)
        self.assertEqual((result["ranks"], result["reserves"], result["publications"]), (36, 1, 1))
        self.assertEqual(
            result["sha256"],
            hashlib.sha256(b"".join(A["RECORD"].pack(*r) for r in rows)).hexdigest(),
        )
        for kind, alter in (
            (17, "drop"),
            (17, "duplicate"),
            (27, "drop"),
            (27, "duplicate"),
            (11, {"a": 0}),
            (17, {"gen": 2}),
            (7, {"b": 101}),
            (2, {"c": 1}),
        ):
            with self.subTest(kind=kind, alter=alter):
                copy = rows.copy()
                i = next(i for i, r in enumerate(copy) if r.kind == kind)
                if alter == "drop":
                    copy.pop(i)
                elif alter == "duplicate":
                    copy.insert(i, copy[i])
                else:
                    copy[i] = copy[i]._replace(**alter)
                with self.assertRaises(ValueError):
                    self.grade(copy)

    def test_geometry_and_capacity(self):
        self.assertEqual((len(A["T1"]), sum(A["T1"])), (86, 2120))
        self.assertEqual(sum((n + 31) // 32 for n in A["T1"]), 141)
        self.assertLess(A["max_prefix_records"](), A["CAP"])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "data"
            p.touch(mode=0o600)

            def write(cut, flags=0, attempted=0, saved=0):
                with p.open("r+b") as f:
                    f.write(
                        A["HEADER"].pack(A["MAGIC"], 1, 96, A["CAP"], attempted, saved, flags, cut)
                    )
                    f.truncate(64 + A["CAP"] * 96)

            write(0)
            with self.assertRaises(ValueError):
                A["seal_before_post"](p)
            write(A["CAP"] - A["T2_CAP"] + 1)
            with self.assertRaises(ValueError):
                A["metadata"](p, False)
            write(42)
            self.assertEqual(A["metadata"](p, False), (42, 0))
            with self.assertRaises(ValueError):
                A["metadata"](p, True)
            write(0, 3, 12, 11)
            with self.assertRaises(ValueError):
                A["metadata"](p, True)


if __name__ == "__main__":
    unittest.main()
