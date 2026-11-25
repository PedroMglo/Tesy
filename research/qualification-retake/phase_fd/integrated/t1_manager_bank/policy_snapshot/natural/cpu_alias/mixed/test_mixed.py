"""Model-free checks of source provenance and the trial's failure conditions."""

import struct
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

    def test_negative_must_localize(self):
        zero = bytes(review["COUNT"] * 8)
        changed = bytearray(zero)
        struct.pack_into("<I", changed, 0, 123456)
        delta = review["changes"](zero, changed)
        self.assertEqual(delta, [{"0,0,0": 1}, {}])
        struct.pack_into("<I", changed, 2880 * 4, 123456)  # another slot
        with self.assertRaises(ValueError):
            review["changes"](zero, changed)

    def test_generation_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out"
            lines = [f"EPOCH {i + 1} {i % 2} 7 {int(i != 0)} 103680" for i in range(4)]
            path.write_text("\n".join(lines))
            self.assertEqual(len(runner["parse_epochs"](path, "alias", None)), 4)
            path.write_text("\n".join(lines[:-1] + [lines[0]]))
            with self.assertRaises(ValueError):
                runner["parse_epochs"](path, "alias", None)


if __name__ == "__main__":
    unittest.main()
