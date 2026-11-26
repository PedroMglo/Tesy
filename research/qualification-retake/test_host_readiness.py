import errno
import hashlib
import tempfile
import unittest
from pathlib import Path

from host_readiness import BLOCK, digest_direct


class DirectContentIdentity(unittest.TestCase):
    def test_tail_and_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model-free.bin"
            data = bytes(BLOCK) + b"final-short-block"
            path.write_bytes(data)
            expected = hashlib.sha256(data).hexdigest()
            try:
                result = digest_direct(path, len(data), expected)
            except OSError as exc:
                if exc.errno in {errno.EINVAL, errno.EOPNOTSUPP}:
                    self.skipTest("filesystem lacks direct I/O")
                raise
            self.assertEqual((result["size_bytes"], result["sha256"]), (len(data), expected))
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                digest_direct(path, len(data) + 1, expected)
            path.write_bytes(data[:-1] + b"!")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                digest_direct(path, len(data), expected)
