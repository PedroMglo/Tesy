"""Reject incorrect capture edges and single-bit or nonfinite row mutations."""

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

PROFILE = run_path(Path(__file__).with_name("profile.py"))
VERIFY = PROFILE["verify_projection"]


class ProjectionChecks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        source = str(Path(__file__).resolve())
        self.row = {"providers": {"cpu": source, "base": source}}
        self.proof = dict(
            status="PASS_CPU0_E28_GATE_AND_SINGLE_RANK",
            source="original_gate_mmid_before_add_id",
            shape=[2880, 4, 1, 1],
            positions=1,
            rank=0,
            expert=28,
            slot=3,
            generation=6,
            gate_observations=1,
            bias_edges=1,
            finite_values=2880,
            unequal_single=0,
            x_sha256=PROFILE["X"],
            weight_sha256=PROFILE["WEIGHT"],
            provider_cpu=source,
            provider_base=source,
        )
        self.write("gate-rank0.f32", "gate_sha256", bytes(11520))
        self.write("single-rank0.f32", "single_sha256", bytes(11520))
        self.write("activation.q8", "q8_sha256", bytes(3060))

    def write(self, name, key, data):
        (self.d / name).write_bytes(data)
        self.proof[key] = hashlib.sha256(data).hexdigest()

    def verify(self):
        (self.d / "gate.json").write_text(json.dumps(self.proof))
        return VERIFY(self.d, self.row)

    def test_valid(self):
        self.assertEqual(self.verify(), self.proof)

    def test_signed_zero(self):
        self.write(
            "single-rank0.f32", "single_sha256", struct.pack("<I", 0x80000000) + bytes(11516)
        )
        with self.assertRaisesRegex(ValueError, "bitwise"):
            self.verify()

    def test_both_nan(self):
        raw = struct.pack("<I", 0x7FC00001) + bytes(11516)
        self.write("single-rank0.f32", "single_sha256", raw)
        self.write("gate-rank0.f32", "gate_sha256", raw)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.verify()

    def test_missing_bias_edge(self):
        self.proof["bias_edges"] = 0
        with self.assertRaisesRegex(ValueError, "bias_edges"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
