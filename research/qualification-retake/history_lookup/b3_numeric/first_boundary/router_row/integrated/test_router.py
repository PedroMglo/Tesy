import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import binding  # noqa: E402
import evaluate  # noqa: E402

driver = evaluate.load(HERE / "profile.py", "integrated_run")


class RouterTests(unittest.TestCase):
    def test_dimensions_and_absence(self):
        base = list(evaluate.cuts("OFF"))
        on = list(evaluate.cuts("ON"))
        ar = list(evaluate.cuts("AR"))
        self.assertEqual(len(base), 383)
        self.assertEqual(base, ar)
        changed = [(old, new) for old, new in zip(base, on, strict=True) if old != new]
        self.assertEqual(len(changed), 36)
        for (layer, old, s), (layer2, new, t) in changed:
            self.assertEqual(
                (layer, old, s.name, s.ops), (layer2, new, "ffn_moe_logits", ("MUL_MAT",))
            )
            self.assertEqual(t.ops, ("CONCAT",))
        self.assertEqual(14 * 3 + 22 * 2, 86)
        self.assertEqual(36 * 3 - 86, 22)

    def test_no_observer_relaxation(self):
        source = driver.builder.source.client().decode()
        self.assertIn("width==3", source)
        self.assertIn("router && width==3", source)
        self.assertIn("t->op==GGML_OP_CONCAT", source)
        self.assertIn('cuts.emplace("ffn_moe_logits-"+std::to_string(il)', source)
        self.assertIn("else if (t->op != c.op && t->op != c.alt)", source)

    def test_monitor_patch_only_child(self):
        repo = Path("/repo")
        original = [
            "/usr/bin/env",
            "-i",
            "LD_LIBRARY_PATH=/monitor",
            "python",
            "/repo/tools/run_bounded.py",
            "--env",
            "LD_LIBRARY_PATH=/r0",
            "--",
            "executable",
        ]
        for mode in ("OFF", "AR", "ON"):
            cmd = binding.adjust(original, repo, "/r0", "/candidate:/r0", mode)
            self.assertEqual(cmd[:4], original[:4])
            self.assertIn("LD_LIBRARY_PATH=/candidate:/r0", cmd)
            self.assertEqual("TESY_B3_ROUTER_ROW=1" in cmd, mode == "ON")
        with self.assertRaises(ValueError):
            binding.adjust(original, repo, "/wrong", "/candidate:/r0", "ON")
        with self.assertRaises(ValueError):
            binding.adjust(original, repo, "/r0", "/candidate:/r0", "B3")

    def test_reject_on_wrong_switch(self):
        e = {
            "LD_DEBUG": "libs",
            "LD_DEBUG_OUTPUT": "/logs",
            "LD_LIBRARY_PATH": "/l",
            "TESY_CPU_WAVE_SKIP_PARKED": "1",
            binding.FLAG: "1",
        }
        m = {"explicit_env": e, "relevant_environment": e | {binding.FLAG: "0"}}
        with self.assertRaisesRegex(ValueError, "effective router"):
            binding.monitor_check(m, {}, e, "ON", None)
        with self.assertRaisesRegex(ValueError, "effective router"):
            binding.monitor_check(m, {}, e, "OFF", None)

    def test_optional_requires_positive_gate(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            driver.save(folder / "receipt.json", {"status": "DIFFERENT_AT_OBSERVED_CUT_OR_OUTPUT"})
            a = SimpleNamespace(
                completed_pair=folder, completed_pair_sha256=evaluate.sha(folder / "receipt.json")
            )
            with self.assertRaisesRegex(ValueError, "not admissible"):
                driver.prior_pair(a)
            a.completed_pair_sha256 = "123"
            with self.assertRaisesRegex(ValueError, "authority"):
                driver.prior_pair(a)

    def test_first_keeps_sibling_outputs(self):
        def row(p, layer, g, n):
            return dict(position=p, layer=layer, group=g, changed_words=n)

        rows = [row(189, 1, 6, 0), row(189, 1, 7, 1), row(190, 2, 2, 3), row(190, 2, 2, 5)]
        result = evaluate.frontiers(rows)
        self.assertEqual(result["all"], [rows[1]])
        self.assertEqual(result["190"], rows[2:])
        self.assertEqual(result["191"], [])


if __name__ == "__main__":
    unittest.main()
