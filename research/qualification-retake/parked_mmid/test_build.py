import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("parked_build", HERE / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildTests(unittest.TestCase):
    def test_linker_rewrites_every_output_without_changing_flags(self):
        old = build.OBJECT
        line = (
            ": && /usr/bin/g++-15 -shared -o " + build.TARGET + " "
            "-Wl,--dependency-file=ggml/src/CMakeFiles/ggml-cpu.dir/link.d " + old + " && :"
        )
        out = Path("/private")
        with patch.object(build, "LINK_SHA", build.sha_text(line)):
            self.assertEqual(
                build.linker(line, out, out / "object"),
                [
                    "/usr/bin/g++-15",
                    "-shared",
                    "-o",
                    str(out / build.CPU),
                    "-Wl,--dependency-file=/private/link.d",
                    "/private/object",
                ],
            )
        with self.assertRaises(ValueError):
            build.linker(line + " other", out, old)

    def test_wrong_or_duplicate_object_rejected(self):
        for args in (["missing"], ["object", "object"]):
            with self.assertRaises(ValueError):
                build.replace(args, "object", "/private")

    def test_synthetic_rows_check_mode_coverage_and_bits(self):
        zero = bytes(98304)
        on = "PASS_PARKED_MMID_GRAPH cases=192 skipped=24 rows_bytes=98304\n"
        off = on.replace("skipped=24", "skipped=0")
        self.assertEqual(build.validate_graph("off", off, zero, None)["bytes"], len(zero))
        self.assertEqual(build.validate_graph("on", on, zero, zero)["bytes"], len(zero))
        for args in (
            ("on", off, zero),
            ("r0", on, zero),
            ("off", off, zero[1:]),
            ("on", on, bytes([1]) + zero[1:]),
        ):
            with self.assertRaises(ValueError):
                build.validate_graph(*args, zero)


if __name__ == "__main__":
    unittest.main()
