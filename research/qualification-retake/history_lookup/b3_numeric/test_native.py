"""Review the reused R0 parameter values and the output-row API without loading weights."""

import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
NATIVE = (HERE / "native.cpp").read_text()
# The builder independently pins the actual C270 capture TU and its direct reader.
# These public C127 parameter assignments also apply to the C210 reader variant.
C127 = (HERE.parents[3] / "tools/c127_slots40_boundary_capture.cpp").read_text()


def assignments(source, object_name):
    return {
        name: value.strip()
        for name, value in re.findall(rf"\b{object_name}\.(\w+)\s*=\s*(?!=)([^;]+);", source)
        if name not in {"cb_eval", "cb_eval_user_data"}
    }


class Native(unittest.TestCase):
    def test_model_and_context_profile(self):
        for name in ("mp", "cp"):
            self.assertEqual(assignments(NATIVE, name), assignments(C127, name))
        self.assertIn("cp.n_outputs_max==0", NATIVE)
        self.assertIn("cp.cb_eval=Observer::callback", NATIVE)
        self.assertIn("#include TESY_B3_PARENT_CAPTURE", NATIVE)

    def test_historical_reference_positions(self):
        self.assertIn("state.enabled = i == 0 || i == 1 || i == 7 || i == 31", C127)
        self.assertIn("continuation[static_cast<size_t>(i)]", C127)
        self.assertIn("static_cast<int>(prompt.size()) + i, 1", C127)

    def test_every_verifier_row_is_exposed(self):
        self.assertIn("batch.logits[i]=1", NATIVE)
        self.assertIn("batch.pos[i]=189+rows[i]", NATIVE)
        self.assertIn("llama_get_logits_ith(ctx,i)", NATIVE)
        self.assertIn("llama_get_logits_ith(ctx.get(),-1)", NATIVE)
        self.assertIn("observer.ffn==width && observer.projection==width", NATIVE)
        self.assertNotIn("llama_memory_seq_rm(", NATIVE)

    def test_save_before_rejecting_nonfinite(self):
        start = NATIVE.index("void write_row(")
        save = NATIVE.index("write_new(path,row,", start)
        self.assertLess(save, NATIVE.index("check(finite_row(", start))

    def test_order_of_state_and_carry(self):
        start = NATIVE.index("prefix_agreement(out,gold)")
        steps = [
            'out/"initial-pool.bin"',
            'out/"initial-kv.bin"',
            "if (!ar)",
            'same_file(out/"initial-pool.bin",gold/"initial-pool.bin")',
            'same_file(out/"initial-kv.bin",gold/"initial-kv.bin")',
            "observer.verifying=true",
            "continuation,0,3,out",
            'out/"post3-kv.bin"',
            "continuation,3,1,out",
        ]
        for expression in steps:
            start = NATIVE.index(expression, start) + len(expression)
