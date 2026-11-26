import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("uncounted_fusion_builder", PATH)
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class CounterRemoval(unittest.TestCase):
    def test_exact_two_spans_and_source_identity(self):
        plain = b"before\nmiddle\nafter\n"
        marked = b"before\n" + build.DEFINITION + b"middle\n" + build.INCREMENT + b"after\n"
        with (
            patch.object(build, "COUNTED_SOURCE", build.digest(marked)),
            patch.object(build, "TIMING_SOURCE", build.digest(plain)),
        ):
            self.assertEqual(build.uncount(marked), plain)
            with self.assertRaisesRegex(ValueError, "translation unit mismatch"):
                build.uncount(marked.replace(b"middle", b"altered"))
        twice = marked + build.INCREMENT
        with patch.object(build, "COUNTED_SOURCE", build.digest(twice)):
            with self.assertRaisesRegex(ValueError, "counter spans"):
                build.uncount(twice)


if __name__ == "__main__":
    unittest.main()
