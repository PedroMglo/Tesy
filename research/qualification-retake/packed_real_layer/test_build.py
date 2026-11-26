"""No weights, compiler, or hardware: authenticate and isolate the canonical FFN sequence."""

import os
import tempfile
import unittest
from pathlib import Path

import build


class TestCanonicalPortion(unittest.TestCase):
    def test_immutable_projection_and_rank_sequence(self):
        repo = Path(
            os.environ.get("TESY_TEST_REPO") or Path(__file__).resolve().parents[3]
        )
        text = build.functions(repo / "tools/block_expert_reuse_operator.cpp")
        self.assertLess(
            text.index("ggml_mul_mat_id(c,t[1]"), text.index("ggml_mul_mat_id(c,t[0]")
        )
        self.assertLess(
            text.index("ggml_mul_mat_id(c,t[0]"), text.index("ggml_swiglu_oai")
        )
        self.assertLess(
            text.index("ggml_swiglu_oai"), text.index("ggml_mul_mat_id(c,t[2]")
        )
        self.assertEqual(text.count("for(int k=0;k<4;++k)"), 1)
        self.assertNotIn("ggml_backend_tensor_set(", text)
        self.assertNotIn("void build(graph_plan", text)

    def test_changed_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operator.cpp"
            path.write_text("ggml_mul_mat_id(c,t[0],inp,ids);")
            with self.assertRaisesRegex(ValueError, "source changed"):
                build.functions(path)


if __name__ == "__main__":
    unittest.main()
