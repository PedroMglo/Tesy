import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gate
import run_pair


def synthetic_routes():
    data = bytearray(b"TPR1")
    for call, positions in [(1, list(range(16))), (2, [16]), (3, [17])]:
        data += b"C" + struct.pack("<HH", call, len(positions))
        data += b"U" + struct.pack("<HB", 1, len(positions))
        for pos in positions:
            data += struct.pack("<HB", pos, int(pos == positions[-1]))
        for layer in range(36):
            count = len(positions) if layer < 35 else 1
            data += b"R" + bytes([layer]) + (b"M" if count > 1 else b"S")
            data += bytes([count]) + bytes([1, 7, 9, 10]) * count
        data += b"ED" + {1: b"P", 2: b"I", 3: b"F"}[call]
    return bytes(data)


class CanaryGateTest(unittest.TestCase):
    def test_cap_admission_keeps_other_guards_and_both_memory_estimates(self):
        mem = {"cap_max_bytes": run_pair.CAP}
        w = {
            "status": "NOT_ADMITTED",
            "reason": ["HOST_CAP_PLUS_RESERVE_UNAVAILABLE"],
            "canonical_policy_sha256": "known",
            "memory": mem,
            "canonical_memory": mem,
        }
        p = {"memory": mem}
        run_pair.admit_window(w, p, "known")
        with self.assertRaises(run_pair.NotAdmitted):
            run_pair.admit_window(dict(w, memory={"cap_max_bytes": run_pair.CAP - 1}), p, "known")
        with self.assertRaises(run_pair.NotAdmitted):
            run_pair.admit_window(dict(w, reason=["CONCURRENT_JOB"]), p, "known")
        with self.assertRaises(ValueError):
            run_pair.admit_window(w, p, "wrong")

    def test_journal_shape_and_missing_cut(self):
        data = synthetic_routes()
        result = gate.routes(data)
        self.assertEqual(result["groups"], 633)
        self.assertEqual(result["counts_by_path"], {"M": 560, "S": 73})
        with self.assertRaises(ValueError):
            gate.routes(data.replace(b"EDP", b"ED"))
        with self.assertRaises(ValueError):
            gate.routes(data[:-1])

    def test_missing_and_invalid_logits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prefix = root / "synthetic"
            gold = bytes(gate.SIZE)
            ref = mock.patch.object(gate, "reference", return_value=([8, 10], gold))
            with ref, mock.patch.object(gate, "DIGEST", gate.hashed(gold)):
                with self.assertRaises(FileNotFoundError):
                    gate.numerical(root, prefix, "OFF")
                logits = root / "synthetic.logits.f32"
                for bad in [gold[:4], struct.pack("<f", float("nan")) + gold[4:], b"x" + gold[1:]]:
                    logits.write_bytes(bad)
                    with self.assertRaises(ValueError):
                        gate.numerical(root, prefix, "OFF")
                logits.write_bytes(gold)
                steps = root / "synthetic.steps.tsv"
                valid = "step\tposition\ttoken_id\tcompletion_s\n0\t16\t8\t1.0\n1\t17\t10\t2.0\n"
                steps.write_text(valid.replace("17\t10", "17\t9"))
                with self.assertRaisesRegex(ValueError, "teacher-forced"):
                    gate.numerical(root, prefix, "OFF")
                steps.write_text(valid)
                (root / "synthetic.ops.tsv").write_text(
                    "arm\tprompt_tokens\tcontinuation_tokens\tlogit_rows\nC\t16\t2\t3\n"
                )
                self.assertEqual(gate.numerical(root, prefix, "OFF")["mode"], "OFF")
                with self.assertRaises(FileNotFoundError):
                    gate.numerical(root, prefix, "ON")
                (root / "synthetic.routes.bin").write_bytes(synthetic_routes())
                with self.assertRaisesRegex(ValueError, "OFF emitted"):
                    gate.numerical(root, prefix, "OFF")
                self.assertEqual(gate.numerical(root, prefix, "ON")["routing"]["groups"], 633)
