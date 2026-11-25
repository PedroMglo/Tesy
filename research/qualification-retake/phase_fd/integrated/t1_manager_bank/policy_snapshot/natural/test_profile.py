import os
import tempfile
import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
profile = run_path(HERE / "profile.py")
a = profile["acq"]


class NaturalPolicy(unittest.TestCase):
    def test_live_fd_identity_and_access(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "policy.bin"
            number = os.open(f, os.O_WRONLY | os.O_EXCL | os.O_CREAT | os.O_CLOEXEC, 0o600)
            try:
                witness = a["owned_file"](f, os.getpid(), os.O_WRONLY, 0)
                self.assertEqual(witness["ino"], f.stat().st_ino)
                self.assertEqual(witness["fd"], number)
                with self.assertRaises(ValueError):
                    a["owned_file"](f, os.getpid(), os.O_RDWR, 0)
                duplicate = os.dup(number)
                try:
                    with self.assertRaises(ValueError):
                        a["owned_file"](f, os.getpid(), os.O_WRONLY, 0)
                finally:
                    os.close(duplicate)
            finally:
                os.close(number)
            with self.assertRaises(ValueError):
                a["owned_file"](f, os.getpid(), os.O_WRONLY, 0)

    def test_rank_order_and_graph_geometry(self):
        def row(kind, call=2, value=1):
            return SimpleNamespace(kind=kind, call=call, tile=1, layer=0, wave=0, a=value, b=4, c=3)

        def view(rows):
            return a["structural"](rows, rows[0].call)

        base = [row(k) for k in [1, 3, 9, 27, 27]]
        ref = view(base)
        self.assertEqual(ref, view([row(r.kind, 19) for r in base] + [row(17)]))
        self.assertNotEqual(
            ref["t2_route_sha256"], view(base[:-1] + [row(27, value=2)])["t2_route_sha256"]
        )
        self.assertNotEqual(
            ref["t2_geometry_sha256"],
            view([*base[:2], row(9, value=2), *base[3:]])["t2_geometry_sha256"],
        )

    def test_noncanonical_and_pending_sidecars(self):
        snap = a["snapshot"]
        e = SimpleNamespace(kind=1, call=2, a=5, b=2044, c=2048)
        header = [b"TPOLICY1", 1, 1, 2, 5, 2044, 2048, 2500, 2304, 4, 36, 40, 128, 0, 0, 0]
        layer = (10, *([1] * 40), *([42] * 128))
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "policy.bin"
            for index, wrong in [(None, None), (3, 1), (15, 1)]:
                data = header.copy()
                if index is not None:
                    data[index] = wrong
                f.write_bytes(snap.HEADER.pack(*data) + snap.LAYER.pack(*layer) * 36)
                if index is None:
                    self.assertEqual(a["verify_sidecar"](f, e)["matches"], 1)
                else:
                    with self.assertRaises(ValueError):
                        a["verify_sidecar"](f, e)


if __name__ == "__main__":
    unittest.main()
