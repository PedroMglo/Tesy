"""Model-free counterexamples for transport selection, FD identity and the exit witness."""

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path

profile = run_path(Path(__file__).with_name("transport_profile.py"))
live = profile["live"]


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc = self.root / "proc"
        self.proc.mkdir()
        for name in ("fd", "fdinfo"):
            (self.proc / name).mkdir()
        self.paths = {k: self.root / k for k in ("pack", "model", "manifest")}
        for p in self.paths.values():
            p.write_bytes(b"fixture")
        self.stats = {k: live.static.derive.runtime_stat(p.stat()) for k, p in self.paths.items()}
        self.environ(False)

    def environ(self, on):
        value = (
            (live.STORE_ENV + "=" + str(self.paths["manifest"])).encode() if on else b"PATH=/bin"
        )
        (self.proc / "environ").write_bytes(value + b"\0")

    def desc(self, n, key, flags=os.O_RDONLY | os.O_DIRECT):
        target = self.paths[key] if isinstance(key, str) else key
        (self.proc / "fd" / str(n)).symlink_to(target)
        (self.proc / "fdinfo" / str(n)).write_text("flags:\t" + oct(flags) + "\n")

    def check_cut(self, mode):
        return profile["cut"](self.proc, self.paths, self.stats, mode)

    def test_paths_and_actual_open_modes(self):
        self.desc(4, "model")
        self.assertEqual(self.check_cut("R"), self.check_cut("O"))
        self.environ(True)
        with self.assertRaisesRegex(ValueError, "cardinality"):
            self.check_cut("P")
        self.desc(8, "pack")
        self.assertEqual(self.check_cut("P")["pack"], [{"fd": 8, "flags": os.O_DIRECT}])
        self.environ(False)
        with self.assertRaisesRegex(ValueError, "cardinality"):
            self.check_cut("O")
        self.environ(True)
        self.desc(9, "pack")
        with self.assertRaisesRegex(ValueError, "cardinality"):
            self.check_cut("P")

    def test_other_name_of_same_inode(self):
        alias = self.root / "alias"
        os.link(self.paths["pack"], alias)
        self.stats["pack"] = live.static.derive.runtime_stat(alias.stat())
        self.desc(4, "model")
        self.desc(5, alias)
        self.environ(True)
        with self.assertRaisesRegex(ValueError, "foreign"):
            self.check_cut("P")

    def test_buffered_writable_and_missing_env(self):
        self.desc(4, "model")
        self.desc(5, "pack", os.O_RDONLY)
        with self.assertRaisesRegex(ValueError, "environment"):
            self.check_cut("P")
        self.environ(True)
        for bits in (os.O_RDONLY, os.O_DIRECT | os.O_RDWR, os.O_DIRECT | os.O_PATH):
            (self.proc / "fdinfo" / "5").write_text("flags:\t" + oct(bits) + "\n")
            with self.assertRaisesRegex(ValueError, "buffered or writable"):
                self.check_cut("P")

    def test_c55_expires_before_launch(self):
        now = datetime.now(UTC)
        age = profile["c55_age"]
        self.assertEqual(age((now - timedelta(seconds=3299)).isoformat(), now), 3299)
        for delta in (-1, 3300, 3600):
            with self.assertRaisesRegex(ValueError, "C55"):
                age((now - timedelta(seconds=delta)).isoformat(), now)

    def test_exactly_one_replacement(self):
        old = {"image": live.static.C269, "cpu": "same"}
        new = old | {"image": live.static.C291}
        select = profile["bound_startup"]
        self.assertEqual(select(old, new, "image", "R"), old)
        self.assertEqual(select(old, new, "image", "O"), new)
        self.assertEqual(select(old, new, "image", "P"), new)
        for broken in (old, new | {"extra": "foreign"}, new | {"cpu": "alternate"}):
            with self.assertRaisesRegex(ValueError, "provider delta"):
                select(old, broken, "image", "P")

    @unittest.skipUnless(hasattr(os, "pidfd_open"), "Linux pidfd required")
    def test_exit_witness(self):
        rt = profile["Runtime"].__new__(profile["Runtime"])
        rt.exit_observed_ns = None
        with subprocess.Popen(
            [sys.executable, "-IB", "-c", "input()"], stdin=subprocess.PIPE
        ) as child:
            rt.watch_exit(child.pid)
            child.communicate(b"exit\n", timeout=5)
            rt.exit_thread.join(timeout=2)
        self.assertIsInstance(rt.exit_observed_ns, int)


if __name__ == "__main__":
    unittest.main()
