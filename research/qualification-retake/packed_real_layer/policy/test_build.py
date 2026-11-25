"""Prevent numerical controls from silently sharing candidate victim selection."""

import unittest

import build


class TestIsolation(unittest.TestCase):
    def test_stock_body_and_opt_in_only(self):
        orig = (
            "int32_t llama_moe_stream::pick_victim_locked(){\n"
            "    int32_t v = -1;\n    return v;\n}\n"
            "void llama_moe_stream::reserve_slot_locked("
        )
        gate = "if (policy_use_backing) {\n    if (!empty && backed) keep=filtered.data();\n}\n"
        candidate = orig.replace("    int32_t v", gate + "    int32_t v")
        build.victim_guard(orig, candidate)
        for altered in [
            candidate.replace("if (policy_use_backing) {", "{"),
            candidate.replace("return v;", "return v+1;"),
            candidate.replace("if (!empty && backed)", "if (backed)"),
            candidate.replace(
                "if (policy_use_backing)", "keep=filtered.data(); if (policy_use_backing)"
            ),
        ]:
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                build.victim_guard(orig, altered)

    def test_sealed_input_graphs(self):
        for name, expected in build.PARENT.items():
            self.assertEqual(build.sha(build.HERE.parent / name), expected)
        src = build.tile.functions(build.HERE.parents[3] / "tools/block_expert_reuse_operator.cpp")
        self.assertEqual(src.count("ggml_add_id("), 3)
