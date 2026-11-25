"""Refuse changes to the C269 attribution and syscall seams before private builds."""

import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("phase_fd_native", HERE / "native.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
HEADER = (HERE / "phase-fd-integrated.h").read_text()
PATCH = (HERE / "native.patch").read_text()


class SourceContract(unittest.TestCase):
    def test_binary_schema_and_off(self):
        self.assertEqual(struct.calcsize("<8s7Q"), 64)
        self.assertEqual(struct.calcsize("<QQQqqq12i"), 96)
        self.assertIn("if (!file) return;", HEADER)
        self.assertLess(
            HEADER.index("if (!file) return;"), HEADER.index("std::make_unique<Journal>")
        )
        self.assertIn("O_CREAT|O_EXCL|O_NOFOLLOW", HEADER)
        self.assertIn("if(!journal || job.worker<0) return ::pread", HEADER)
        self.assertIn("errno=error;", HEADER)
        self.assertNotIn("cb_eval", PATCH)
        self.assertNotIn("llama_synchronize(", PATCH)
        self.assertIn("::pread(fd,dst,requested,offset)", HEADER)

    def test_origin_and_wait_sources(self):
        self.assertIn("journal->origin[sl.il][slot]=s;", HEADER)
        self.assertIn("journal->origin[w.sl->il][w.slot].gen==w.gen", HEADER)
        self.assertIn("!computing || !host.call", HEADER)
        self.assertEqual(PATCH.count("pfj::consumer("), 2)
        self.assertEqual(PATCH.count("pfj::finish_consumer();"), 2)
        self.assertEqual(PATCH.count("pfj::BARRIER_ENTER"), 2)
        self.assertEqual(PATCH.count("pfj::BARRIER_RETURN"), 2)
        self.assertEqual(PATCH.count("pfj::enqueue("), 5)
        self.assertEqual(PATCH.count("pfj::read(fd"), 2)
        self.assertIn("if (pfj::journal) pfj::dispatched(w,false);", PATCH)
        self.assertIn("pfj::finish(this)", PATCH)
        self.assertLess(PATCH.index("w.join();"), PATCH.index("pfj::finish(this)"))

    def test_reject_other_pin(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            import subprocess

            subprocess.run(["git", "init", "-q", root], check=True)
            with self.assertRaises(subprocess.CalledProcessError):
                native.materialize(root, root / "overlay")
            self.assertFalse((root / "overlay").exists())
