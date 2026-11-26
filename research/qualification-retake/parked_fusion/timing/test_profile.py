import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "parked_fusion_timing", Path(__file__).with_name("profile.py")
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class TimingProfile(unittest.TestCase):
    def test_selection_and_position_balance(self):
        decide = p.load("parked_decision_test", p.HERE / "decision.py")
        rows = [
            dict(
                mode=m,
                run_index=i,
                phase="qualification" if i < 3 else "timing",
                block=None if i < 3 else (i - 3) // 3,
                graph_ns=2**50 if i < 3 else i * 104729,
                child_started=True,
                returncode=0,
                status="PASS_TILE",
                tile_sha256=p.GOLD,
                tile_bytes=p.TILE_BYTES,
            )
            for i, m in enumerate(p.ORDER)
        ]
        result = p.timings(rows, decide)
        self.assertEqual(result, decide.evaluate(rows[3:]))
        self.assertEqual(len(result["blocks"]), 6)
        for index in range(3):
            self.assertEqual(Counter(b[index] for b in p.BLOCKS), {m: 2 for m in p.MODES})
        for i, change in (
            (0, {"tile_bytes": 0}),
            (9, {"block": 1}),
            (18, {"mode": "MMID"}),
            (20, {"status": "FAIL_PRESERVED"}),
        ):
            with self.subTest(index=i), self.assertRaises(ValueError):
                p.timings(rows[:i] + [rows[i] | change] + rows[i + 1 :], decide)

    def test_partial_archive_is_sealed_and_private_paths_do_not_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "receipt.json"
            raw = dict(
                status="FAIL_PRESERVED",
                reason="unexpected provider /private/location/file",
                elapsed_s=0.2,
                supervisor_sha256=p.digest(p.HERE / "profile.py"),
                arms=[
                    dict(
                        run_index=0,
                        mode="ORIGINAL",
                        status="FAIL_PRESERVED",
                        child_started=True,
                        returncode=1,
                        private_path="/private/location/file",
                    )
                ],
            )
            path.write_text(json.dumps(raw))
            digest = p.digest(path)
            out = p.verify(root, digest)
            self.assertEqual(out["preserved_arms"][0]["returncode"], 1)
            self.assertNotIn("/private", json.dumps(out))
            path.write_text(json.dumps(raw | {"status": p.PASS}))
            with self.assertRaisesRegex(ValueError, "terminal receipt"):
                p.verify(root, digest)


if __name__ == "__main__":
    unittest.main()
