"""Model-free checks of source provenance and the trial's failure conditions."""

import struct
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
source = run_path(HERE / "source.py")
review = run_path(HERE / "review.py")
runner = run_path(HERE / "run.py")


class TestMixed(unittest.TestCase):
    def test_graph(self):
        text = source["render"]()
        self.assertEqual(text.count("ggml_backend_sched_alloc_graph(sched.get(),g)"), 1)
        self.assertIn("ggml_backend_cpu_buffer_from_ptr(arena->base(), capacity)", text)
        self.assertIn("w==s.weight", text)
        self.assertLess(
            text.index("ggml_backend_sched_alloc_graph(sched.get(),g)"), text.index("arena->rebind")
        )
        self.assertLess(
            text.index("ggml_backend_sched_graph_compute(sched.get(),g)"),
            text.index("ggml_backend_sched_synchronize(sched.get())"),
        )
        self.assertIn("if (packed && slot==39) continue", text)
        self.assertIn("std::_Exit(14)", text)
        self.assertIn("refill(epoch != 0, epoch);", text)
        self.assertIn("differences(input)==0", text)

    def test_negative_must_localize(self):
        zero = bytes(review["COUNT"] * 8)
        changed = bytearray(zero)
        struct.pack_into("<I", changed, 0, 123456)
        delta = review["changes"](zero, changed)
        self.assertEqual(delta, [{"0,0,0": 1}, {}])
        struct.pack_into("<I", changed, 2880 * 4, 123456)  # another slot
        with self.assertRaises(ValueError):
            review["changes"](zero, changed)

    def test_same_pid_and_zero_owner_at_exit(self):
        verify = run_path(HERE / "monitor.py")["monitoring"]
        rows = [
            {
                "phase": phase,
                "elapsed_s": i + 0.1,
                "stage": i,
                "peak_bytes": 1000,
                "observation": {"gpu": {"used_mib": 2}, "gpu_owners": owner},
            }
            for i, (phase, owner) in enumerate(
                zip(
                    ("entry", "active", "finish", "after_exit"), ([], [123], [123], []), strict=True
                )
            )
        ]
        with tempfile.TemporaryDirectory() as temp:
            fp = Path(temp) / "monitor.jsonl"

            def apply():
                raw = "".join(json.dumps(v) + "\n" for v in rows).encode()
                fp.write_bytes(raw)
                return verify(fp, hashlib.sha256(raw).hexdigest())

            self.assertEqual(apply(), rows)
            rows[-1]["observation"]["gpu_owners"] = [123]
            with self.assertRaises(ValueError):
                apply()
            del rows[-1]["observation"]["gpu_owners"]
            with self.assertRaises(KeyError):
                apply()

    def test_generation_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out"
            lines = [f"EPOCH {i + 1} {i % 2} 7 {int(i != 0)} 103680" for i in range(4)]
            lines = [f"INPUT_DELTA {i} 0 0 0 0 0" for i in (2, 3, 4)] + lines
            path.write_text("\n".join(lines))
            self.assertEqual(len(runner["parse_epochs"](path, "alias", None)["epochs"]), 4)
            path.write_text("\n".join(lines[:-1] + [lines[0]]))
            with self.assertRaises(ValueError):
                runner["parse_epochs"](path, "alias", None)


if __name__ == "__main__":
    unittest.main()
