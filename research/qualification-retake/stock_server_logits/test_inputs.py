import struct
import tempfile
import unittest
from pathlib import Path

import inputs


class InputsTests(unittest.TestCase):
    def test_packed_order_and_dimensions(self):
        a = [(5 * i + 3) % 100 for i in range(2009)]
        b = [(3 * i + 7) % 100 for i in range(192)]
        bundle = (
            "prompt\t"
            + ",".join(map(str, a))
            + "\ncontinuation192\t"
            + ",".join(map(str, b))
            + "\n"
        ).encode()
        ids, packed = inputs.decode_fixture(bundle)
        self.assertEqual(ids, a[:16])
        self.assertEqual(struct.unpack("<18i", packed), tuple(ids + b[:2]))
        for bad in (
            b"prompt\t0\n" + bundle,
            bundle.replace(b"3,8,", b"-1,8,", 1),
            bundle.replace(b"3,8,", b"", 1),
            bundle.replace(b"7,10,", b"201088,10,", 1),
        ):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                inputs.decode_fixture(bad)

    def test_pinned_public_source_and_private_mismatch(self):
        self.assertEqual(inputs.digest(inputs.MANIFEST.read_bytes()), inputs.MANIFEST_SHA)
        self.assertEqual(inputs.digest(inputs.REFERENCE.read_bytes()), inputs.REFERENCE_SHA)
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / inputs.FIXTURE_NAME).write_bytes(bytes(9994))
            with self.assertRaisesRegex(ValueError, "C110 bundle"):
                inputs.load_prompt(d)


if __name__ == "__main__":
    unittest.main()
