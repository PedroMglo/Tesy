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

    def test_owner_stage_follows_real_set_and_stays_bounded(self):
        src = build["source"]().decode()
        self.assertLess(src.index('mapped(dir,"start")'), src.index("execute(static_cast<Arm>"))
        self.assertLess(
            src.index("ggml_backend_tensor_set(mask,kept.data()"),
            src.index('mapped(dir, "active")'),
        )

        def run(marker, owners, times=(1.0, 1.1, 1.2, 1.3)):
            records = []
            clock = iter(times)

            def sample(phase, attempt):
                records.append((phase, attempt))
                return owners[len(records) - 1]

            result = case["owner_handoff"](marker, 7, sample, lambda: next(clock), lambda _: None)
            return result, records

        self.assertEqual(run(b"E", [[]]), (1, [("entry", 1)]))
        self.assertEqual(run(b"A", [[], [7]]), (2, [("active", 1), ("active", 2)]))
        self.assertEqual(run(b"F", [[7]]), (1, [("finish", 1)]))
        for marker, owners, reason in (
            (b"E", [[7]], "before CUDA"),
            (b"A", [[], [], []], "absent"),
            (b"F", [[]], "absent"),
            (b"A", [[8]], "foreign"),
        ):
            with self.assertRaisesRegex(ValueError, reason):
                run(marker, owners)
        with self.assertRaisesRegex(ValueError, "deadline"):
            run(b"A", [[7]], (0.0, 2.1))

    def test_independent_mxfp4_scale_and_nibble_order(self):
        audit = run_path(str(HERE / "review.py"))
        # Low nibbles fill columns 0..15, high nibbles 16..31.
        row = bytes([126]) + bytes([0xB2]) * 16  # scale 1/2, low +1, high -1.5
        self.assertEqual(audit["project"](row * 32, [1.0] * 16 + [2.0] * 16), [-16.0] * 32)
        broken = bytes([127]) + row[1:] + row * 31
        self.assertEqual(audit["project"](broken, [1.0] * 16 + [2.0] * 16), [-32.0] + [-16.0] * 31)
        with self.assertRaisesRegex(ValueError, "geometry"):
            audit["project"](row, [1.0] * 32)

    def test_passive_reference_identity(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = (root / "mapped.so").resolve()
            name.write_bytes(bytes(8192))
            table = root / "allowed.tsv"
            build["write_vma_table"](
                table, {"test": name}, {str(name): {"ino": name.stat().st_ino}}
            )
            major, minor, ino, target = table.read_text().strip().split()
            self.assertEqual((int(ino), target), (name.stat().st_ino, str(name)))
            self.assertTrue(major.isdecimal() and minor.isdecimal())
            with self.assertRaisesRegex(ValueError, "reference VMA"):
                build["write_vma_table"](root / "bad.tsv", {"test": name}, {str(name): {"ino": 0}})

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
