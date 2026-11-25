import tempfile
import unittest
from pathlib import Path

import build


class SourceBoundaryTest(unittest.TestCase):
    def test_reject_changed_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "bad.cpp").write_bytes(b"not the reference")
            with self.assertRaisesRegex(ValueError, "historical tile"):
                build.apply_layer(
                    root / "bad.cpp", root / "target.cpp", build.HERE / "operator.patch"
                )
            self.assertFalse((root / "target.cpp").exists())

    def test_marker_is_after_original_on_the_executor(self):
        source = (build.HERE / "suffix-clock.h").read_text()
        body = source.split("static void timed_wave_ids", 1)[1].split(
            "static bool valid_boundary", 1
        )[0]
        helper, active = body.split("return;", 1)
        self.assertIn("if (ith != 0)", helper)
        self.assertIn("llama_moe_stream_wave_ids(", helper)
        self.assertNotIn("monotonic_ns()", helper)
        self.assertLess(active.index("llama_moe_stream_wave_ids("), active.index("monotonic_ns()"))
        self.assertEqual(active.count("monotonic_ns()"), 1)

    def test_apply_in_repo(self):
        source = build.HERE.parent / "packed_real_layer/layer.cpp"
        if not source.is_file():
            self.skipTest("exclusive preparation directory outside the repo")
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "layer.cpp"
            build.apply_layer(source, dest, build.HERE / "operator.patch")
            code = dest.read_text()
            self.assertLess(
                code.index("const int64_t start_ns="),
                code.index("ggml_backend_sched_graph_compute(scheduler.get()"),
            )
            self.assertLess(
                code.index("const int64_t end_ns="),
                code.index("const auto found=values<float>(out)"),
            )
            self.assertNotIn("observe,&", code)
            self.assertIn("observed.layer->expert_wave.at(e)==0", code)


if __name__ == "__main__":
    unittest.main()
