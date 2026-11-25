"""Portable preflight and forged-observer rejection. No compiler or GPU."""

import unittest
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
build = run_path(str(HERE / "build.py"))
case = run_path(str(HERE / "run.py"))


class Device(unittest.TestCase):
    def test_source_identity_and_boundaries(self):
        code = build["source"]().decode()
        for boundary in (
            "ggml_backend_event_record(done.get(), gpu.get())",
            "ggml_backend_event_synchronize(done.get())",
            "ggml_backend_sched_graph_compute_async(sched.get(), g)",
            "up->src[0] == weights[2]",
            "poll(&ack, 1, 3000)",
            "ggml_backend_buffer_is_host(t->buffer)",
        ):
            self.assertEqual(code.count(boundary), 1)
        self.assertNotIn("ggml_backend_sched_set_eval_callback", code)
        self.assertNotIn("ggml_backend_graph_compute(cpu", code)
        with self.assertRaisesRegex(ValueError, "identity"):
            build["render"](b"unapproved observer")

    def test_staged_provider_and_gpu_event_required(self):
        paths = {
            n: Path("/sealed") / n
            for n in (
                "libggml-cpu.so.0",
                "libggml-cuda.so.0",
                "libggml-base.so.0",
                "libcuda.so.1",
                "libcudart.so.13",
                "libcublas.so.13",
            )
        }
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            for phase in ("start", "active", "finish", "drain"):
                (d / (phase + ".providers")).write_text(
                    "".join(str(k) + "\n" for k in paths.values())
                )
            self.assertEqual(len(case["verify_maps"](d, paths)), 4)
            (d / "active.providers").write_text(str(paths["libcuda.so.1"]) + "\n")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                case["verify_maps"](d, paths)
            stdout = d / "stdout"
            lines = [
                "GPU_PLACEMENT 3 1 1 1",
                "PROJECTIONS 3",
                "PROVIDER ggml_backend_cpu_init /sealed/libggml-cpu.so.0",
                "PROVIDER ggml_backend_tensor_set /sealed/libggml-base.so.0",
                "GRAPH_DONE",
            ]
            stdout.write_text("\n".join(lines))
            with self.assertRaisesRegex(ValueError, "event"):
                case["parse"](stdout, "event", paths)
            stdout.write_text("\n".join(lines + ["GPU_EVENT_COMPLETED"]))
            self.assertEqual(case["parse"](stdout, "event", paths), ["GRAPH_DONE"])


if __name__ == "__main__":
    unittest.main()
