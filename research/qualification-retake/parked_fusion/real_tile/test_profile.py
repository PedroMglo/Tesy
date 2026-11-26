import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "parked_real_gate", Path(__file__).with_name("profile.py")
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class Gate(unittest.TestCase):
    def test_counter_identity_endpoints_and_joins(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            providers = {}
            for name in ("cpu", "base"):
                file = root / name
                file.write_bytes(name.encode())
                providers[name] = (file, hashlib.sha256(file.read_bytes()).hexdigest())

            def sha(file):
                return hashlib.sha256(file.read_bytes()).hexdigest()

            marker = {
                "counter_pid": 42,
                "counter_present": True,
                "counter_provider": str(root / "cpu"),
                "counter_before": 0,
                "counter_after": 7,
                "counter_delta": 7,
                "providers": {k: str(v[0]) for k, v in providers.items()},
            }
            self.assertEqual(p.counter_gate("FUSION", marker, 42, providers, sha), 7)
            for change in (
                {"counter_pid": 41},
                {"counter_before": 1},
                {"counter_delta": True},
                {"counter_provider": str(root / "base")},
                {"counter_present": False},
            ):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    p.counter_gate("FUSION", marker | change, 42, providers, sha)
            terminal = marker | {"counter_after_graph": 7, "counter_after_join_verified": True}
            p.after_join(terminal, marker)
            for delta in (
                {"counter_after": 8},
                {"counter_after_graph": 6},
                {"counter_after_join_verified": False},
            ):
                with self.assertRaises(ValueError):
                    p.after_join(terminal | delta, marker)
            original = marker | dict.fromkeys(p.COUNTER[2:]) | {"counter_present": False}
            self.assertIsNone(p.counter_gate("ORIGINAL", original, 42, providers, sha))
            with self.assertRaises(ValueError):
                p.counter_gate("OFF", original, 42, providers, sha)

    def test_gold_and_inconclusive_distinguished(self):
        gold = bytes(p.ROW_BYTES)
        self.assertIsNone(p.diff(gold, gold))
        target = bytearray(gold)
        target[12:16] = b"\x00\x00\x00\x80"
        mismatch = p.diff(gold, target)
        self.assertEqual(
            mismatch, dict(f32_index=3, expected_bits=0, observed_bits=0x80000000, nonfinite=False)
        )
        self.assertEqual(p.verdict("FUSION", 7, mismatch), "NO_GO_EXACTNESS")
        self.assertEqual(p.verdict("ORIGINAL", None, mismatch), "INCONCLUSIVE_ORIGINAL_GOLD")
        self.assertIsNone(p.verdict("FUSION", 7, None))
        self.assertEqual(p.verdict("FUSION", 0, None), "INCONCLUSIVE_NOT_APPLIED")
        self.assertEqual(p.verdict("FUSION", 6, None), "INCONCLUSIVE_REGION_COUNT")
        self.assertEqual(p.verdict("MMID", 1, None), "INCONCLUSIVE_ABLATION_COUNT")
        target[12:16] = b"\x00\x00\xc0\x7f"
        self.assertTrue(p.diff(gold, target)["nonfinite"])
        target[0:4] = bytes.fromhex("00000080")
        target[16:20] = bytes.fromhex("0000807f")
        self.assertFalse(p.diff(gold, target)["nonfinite"])
        self.assertEqual(
            p.finiteness(target),
            dict(nonfinite_count=2, first_nonfinite=dict(f32_index=3, observed_bits=0x7FC00000)),
        )


if __name__ == "__main__":
    unittest.main()
