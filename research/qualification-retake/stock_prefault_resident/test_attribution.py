import importlib.util
import tempfile
import unittest
from pathlib import Path

import attribution as attr


def witness(libs):
    groups = []
    for p in range(2):
        groups.extend(
            [
                f"PROVIDER dispatch {libs}/libggml-base.so.0",
                f"PROVIDER kernel {libs}/libggml-cpu.so.0",
                f"EXEC {p} 8 8 8 0 10 0 0 8",
            ]
        )
    return "\n".join(groups)


class AttributionTests(unittest.TestCase):
    def test_execution_providers_and_counterexamples(self):
        libs = Path("/test/libs")
        text = witness(libs)
        self.assertEqual([x["cpu_kernel_returns"] for x in attr.evidence(text, libs)], [8, 8])
        for src, dst in (
            ("0 10 0 0 8", "0 10 1 0 8"),
            ("8 8 8 0", "8 7 8 0"),
            ("8 8 8 0", "8 8 7 0"),
            ("8 8 8 0", "8 8 8 1"),
            ("0 10 0 0 8", "0 10 0 0 7"),
            ("EXEC 1", "EXEC 0"),
            ("libggml-cpu", "lib-other-cpu"),
            ("libggml-base", "lib-other-base"),
            ("0 10 0", "0 0 0"),
            ("8 8 8 0 10 0 0 8", "0 0 0 0 0 0 0 0"),
        ):
            with self.subTest(src=src, dst=dst), self.assertRaises(ValueError):
                attr.evidence(text.replace(src, dst), libs)
        with self.assertRaises(ValueError):
            attr.evidence(text.rsplit("\n", 1)[0], libs)

    def test_program_shape_and_real_symbol_names(self):
        path = attr.guard.UPSTREAM / "tiny_fixture.py"
        spec = importlib.util.spec_from_file_location("tesy_tiny_test", path)
        tiny = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tiny)
        driver = attr.instrument(tiny.DRIVER)
        self.assertEqual(driver.count("if(llama_decode(ctx,batch))"), 1)
        self.assertIn('dlsym(RTLD_NEXT, "ggml_compute_forward_mul_mat")', driver)
        self.assertIn("ggml_backend_get_device(backend)", driver)
        self.assertIn("obs.asked != dst || obs.returned", driver)
        with self.assertRaises(ValueError):
            attr.instrument(driver)

    def test_mismatch_stops_current_arm(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "current"
            r1 = Path(d) / "r1"
            for x in (out, r1):
                (x / "stock").mkdir(parents=True)
                (x / "stock/logits.f32").write_bytes(bytes(256))
            rec = {"arms": {"stock": {}}}
            libs = Path(d)
            check = attr.extend_mapping_check(lambda *args: {"maps": [1]}, out, rec, r1, libs)
            self.assertEqual(check(witness(libs), 100, False), {"maps": [1]})
            (out / "OFF").mkdir()
            (out / "OFF/logits.f32").write_bytes(bytes(255) + b"x")
            with self.assertRaisesRegex(ValueError, "R1 64-logit reference"):
                check(witness(libs), 100, False)


if __name__ == "__main__":
    unittest.main()
