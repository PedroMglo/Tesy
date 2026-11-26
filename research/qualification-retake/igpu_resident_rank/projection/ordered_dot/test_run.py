"""Test byte provenance, launch arguments, exact outputs, padding and the wrong-ID control."""

import struct
import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

RUN = run_path(Path(__file__).with_name("run.py"))


class OrderedSupervisor(unittest.TestCase):
    def setUp(self):
        self.gold = struct.pack("<f", 1.0) * 2880
        self.wrong = bytes(11520)
        self.gpu = bytearray(3312)
        self.cpu = bytes(3060)

    def score(self, correct=None, reference=None):
        return RUN["score_outputs"](
            self.gold if correct is None else correct,
            self.wrong,
            self.gpu,
            self.gpu if reference is None else reference,
            self.gold,
            self.cpu,
        )

    def test_gold_and_one_ulp(self):
        self.assertEqual(self.score()["decision"], "GO_ORDERED_E28_PROJECTION_ONLY")
        mutated = self.gold[:-4] + struct.pack("<I", 0x3F800001)
        result = self.score(mutated)
        self.assertEqual(result["decision"], "NO_GO_BITWISE_ORDERED_PROJECTION")
        self.assertEqual(
            (result["first_unequal"], result["unequal_rows"], result["max_ulp"]), (2879, 1, 1)
        )

    def test_wrong_slot(self):
        self.wrong = self.gold
        with self.assertRaisesRegex(ValueError, "wrong-ID"):
            self.score()

    def test_all_q8_bytes_and_cpu_scale_and_codes(self):
        reference = bytes(self.gpu)
        self.gpu[2] = 1  # The Q8_1 half sum must also match the stock bytes.
        with self.assertRaisesRegex(ValueError, "RHS control"):
            self.score(reference=reference)
        for index in (0, 16):  # Reject matching GPU outputs that disagree with the CPU.
            self.gpu = bytearray(3312)
            self.gpu[index] = 1
            with self.assertRaisesRegex(ValueError, "RHS control"):
                self.score()

    def test_dispatch_argv(self):
        a = SimpleNamespace(build_dir=Path("/stock"), pack=Path("/pack"))
        cmd = RUN["command"](
            a, Path("/x"), Path("/out"), Path("/ordered/gate.spv"), Path("/out/layers"), "testrun"
        )
        exe = cmd.index("/stock/projection")
        self.assertEqual(
            cmd[exe:],
            [
                "/stock/projection",
                "/x",
                "/stock/shared.spv",
                "/stock/subgroup.spv",
                "/out/actual.q8_1",
                "/pack",
                "/ordered/gate.spv",
                "/out/correct.f32",
                "/out/wrong.f32",
            ],
        )
        self.assertEqual(
            cmd[:16],
            [
                "/usr/bin/systemd-run",
                "--user",
                "--scope",
                "--quiet",
                "--unit",
                "testrun",
                "-p",
                "MemoryMax=134217728",
                "-p",
                "MemoryHigh=134217728",
                "-p",
                "MemorySwapMax=0",
                "--",
                "/usr/bin/env",
                "-i",
                "PATH=/usr/bin:/bin",
            ],
        )
        self.assertEqual(cmd[exe - 4 : exe], ["/usr/bin/timeout", "-k", "1s", "9s"])
        self.assertIn("MESA_SHADER_CACHE_DISABLE=true", cmd)
        self.assertIn("VK_LOADER_LAYERS_DISABLE=~implicit~", cmd)


if __name__ == "__main__":
    unittest.main()
