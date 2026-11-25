import tempfile
import unittest
from pathlib import Path

import kernel


class KernelGenerationTest(unittest.TestCase):
    def test_no_destination_on_bad_source(self):
        with tempfile.TemporaryDirectory() as td:
            orig, dest = Path(td) / "original.c", Path(td) / "private.c"
            orig.write_bytes(b"not the C269 file")
            with self.assertRaisesRegex(ValueError, "wrong C269"):
                kernel.materialize(orig, dest)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
