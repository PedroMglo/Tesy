import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import patch

m = run_path(str(Path(__file__).with_name("install_pack.py")))


class Placement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.source = self.parent / "source.bin"
        self.dest = self.parent / "tesy-test.bin"
        self.payload = bytes(range(256)) * 48
        self.source.write_bytes(self.payload)
        self.directory = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.directory)
        self.expected = hashlib.sha256(self.payload).hexdigest()

    def run_copy(self, digest=None, guard=lambda: None):
        result = {}
        m["transfer"](
            self.source,
            self.dest,
            self.directory,
            "test",
            len(self.payload),
            digest or self.expected,
            result,
            guard,
            4096,
        )
        return result

    def test_distinct_historical_readback_authorities(self):
        index = self.parent / "index.json"
        index.touch()
        compact = self.parent / "readback-analysis.json"
        raw = self.parent / "full-readback.json"
        manifest = self.parent / "manifest.json"
        values = {
            manifest: (
                m["MANIFEST"],
                dict(
                    schema="tesy-integral-expert-store-runtime-v1",
                    index_sha256=m["INDEX"],
                    full_readback_sha256=m["READBACK_ANALYSIS"],
                    full_readback_result=str(compact),
                    canonical_model_sha256="target",
                    index_path=str(index),
                    pack_sha256_write_stream=m["DIGEST"],
                    component_count=27648,
                    pack_bytes=m["SIZE"],
                ),
            ),
            index: (
                m["INDEX"],
                dict(
                    schema="tesy-expert-local-integral-store-v1",
                    model_sha256_previous_verified="target",
                    experts=[None] * 4608,
                    store_scope="INTEGRAL_GPT_OSS120B_36x128",
                    logical_bytes=61_073_326_080,
                    pack_path=str(self.source),
                    pack_bytes=m["SIZE"],
                    pack_sha256_write_stream=m["DIGEST"],
                ),
            ),
            raw: (
                m["READBACK"],
                dict(
                    status="PASS_FULL_CANONICAL_PACK_READBACK",
                    component_checks=27648,
                    logical_bytes=61_073_326_080,
                    source_fd_direct=True,
                    pack_fd_direct=True,
                    pack_identity={"size_bytes": m["SIZE"]},
                    pack_sha256_write_stream=m["DIGEST"],
                ),
            ),
            compact: (
                m["READBACK_ANALYSIS"],
                dict(
                    status="PASS_INTEGRAL_STORE_BYTES",
                    index_sha256=m["INDEX"],
                    component_count=27648,
                    pack_sha256_write_stream=m["DIGEST"],
                ),
            ),
        }

        def read(path, digest):
            expected, data = values[path]
            if digest != expected:
                raise ValueError("digest")
            return data

        args = SimpleNamespace(
            runtime_manifest=manifest, index=index, readback=raw, source=self.source
        )
        self.assertEqual(m["authorities"](args, read, "target"), self.source)
        args.readback = compact
        with self.assertRaisesRegex(ValueError, "digest"):
            m["authorities"](args, read, "target")
        args.readback = raw
        values[manifest][1]["full_readback_sha256"] = m["READBACK"]
        with self.assertRaisesRegex(ValueError, "authorities"):
            m["authorities"](args, read, "target")

    def test_independent_readonly_publish(self):
        original = m["identity"](self.source.stat())
        result = self.run_copy()
        self.assertEqual(self.dest.read_bytes(), self.payload)
        self.assertEqual(result["destination_sha256"], result["source_sha256"])
        self.assertEqual(result["destination_reread_bytes"], len(self.payload))
        self.assertFalse(self.dest.stat().st_mode & 0o222)
        self.assertEqual(original, m["identity"](self.source.stat()))
        self.assertEqual(result["destination_stat"], m["identity"](self.dest.stat()))
        self.assertNotEqual(result["destination_stat"]["ino"], original["ino"])
        self.assertFalse((self.parent / result["staging_name"]).exists())

    def test_digest_failure_preserves_source_and_private_staging(self):
        with self.assertRaisesRegex(ValueError, "digest"):
            self.run_copy("0" * 64)
        self.assertFalse(self.dest.exists())
        self.assertEqual((self.parent / ".tesy-test.bin.test.partial").read_bytes(), self.payload)
        self.assertEqual(self.source.read_bytes(), self.payload)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_copy()

    def test_racing_destination_never_replaced(self):
        def clash():
            if not self.dest.exists():
                self.dest.write_bytes(b"owner")

        with self.assertRaises(FileExistsError):
            self.run_copy(guard=clash)
        self.assertEqual(self.dest.read_bytes(), b"owner")
        self.assertEqual((self.parent / ".tesy-test.bin.test.partial").read_bytes(), self.payload)

    def test_corruption_on_independent_reader(self):
        original = os.preadv
        count = 0

        def corrupt(fd, buffers, offset):
            nonlocal count
            n = original(fd, buffers, offset)
            count += 1
            if count == 4:
                buffers[0][0] ^= 1
            return n

        with (
            patch.object(os, "preadv", corrupt),
            self.assertRaisesRegex(ValueError, "destination digest"),
        ):
            self.run_copy()
        self.assertFalse(self.dest.exists())

    def test_symlink_and_guard_fail_closed(self):
        self.dest.symlink_to(self.parent / "absent")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_copy()
        self.dest.unlink()

        def stop():
            raise ValueError("probe resource guard")

        with self.assertRaisesRegex(ValueError, "resource guard"):
            self.run_copy(guard=stop)
        self.assertFalse(self.dest.exists())
        self.assertTrue((self.parent / ".tesy-test.bin.test.partial").exists())


if __name__ == "__main__":
    unittest.main()
