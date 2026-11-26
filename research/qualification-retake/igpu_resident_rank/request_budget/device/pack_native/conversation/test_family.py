import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import family
from family import acquisition as ac


class Admission(unittest.TestCase):
    def test_qualify_toolchain_before_mode_count(self):
        original = family.p.live.static.C291
        base = dict(
            original_sha256=original,
            gold_sha256=original,
            status="PASS_C291_PACK_PFJ_DSO_STATIC_C281",
        )
        self.assertEqual(ac.order_for(base, "exact"), ("BASE", "OFF", "ON"))
        new = base | dict(build_variant="current_compiler_control", control_exec_same=False)
        self.assertEqual(ac.order_for(new, "toolchain"), ("BASE", "CONTROL", "OFF", "ON"))
        self.assertEqual(
            ac.order_for(new | {"control_exec_same": True}, "toolchain"), ("BASE", "OFF", "ON")
        )
        for data, method in (
            (new, "exact"),
            (new | {"control_exec_same": 0}, "toolchain"),
            (new | {"status": "FAIL_PRESERVED"}, "toolchain"),
            (base | {"gold_sha256": "other"}, "exact"),
        ):
            with self.subTest(method=method), self.assertRaises(ValueError):
                ac.order_for(data, method)

    def test_unique_substitution(self):
        original = {str(i): {"file": str(i), "sha256": str(i)} for i in range(23)}
        original[family.p.SONAME] = {"file": "old", "sha256": family.p.live.static.C291}
        now = original | {family.p.SONAME: {"file": "new", "sha256": "SHA"}}
        ac.selected(now, Path("new"), "SHA", original)
        for altered in (original, now | {"0": {"file": "elsewhere", "sha256": "0"}}):
            with self.assertRaises(ValueError):
                ac.selected(altered, Path("new"), "SHA", original)

    def test_original_numeric_bridge_must_not_admit_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            receipt = root / "receipt.json"
            b = {"candidate_sha256": "B", "control_sha256": "A"}
            row = {
                "status": "PASS_C292_PACK_OBSERVER_NUMERIC",
                "build_receipt_sha256": "P",
                "libraries": {
                    "original": family.p.live.static.C291,
                    "control": "A",
                    "overlay": "wrong",
                },
                "arms": {"control_off": {}, "overlay_off": {}, "overlay_on": {}},
            }
            receipt.write_text(json.dumps(row))
            args = SimpleNamespace(bridge_dir=root, bridge_sha256=ac.sha(receipt), build_sha256="P")
            with self.assertRaisesRegex(ValueError, "numeric bridge/ELF identity"):
                ac.bridge(args, b)

    def test_journal_fd_and_absence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "events.pfj"
            (root / "fd").mkdir()
            self.assertIsNone(ac.journal_fd(root, data, False))
            data.touch(mode=0o600)
            with self.assertRaisesRegex(ValueError, "not owned"):
                ac.journal_fd(root, data, True)
            (root / "fd/17").symlink_to(data)
            self.assertEqual(ac.journal_fd(root, data, True)["ino"], data.stat().st_ino)
            with self.assertRaisesRegex(ValueError, "control"):
                ac.journal_fd(root, data, False)
            with self.assertRaisesRegex(ValueError, "environment"):
                ac.observer_env(b"TESY_PHASE_FD_FILE=/other\x00", {})
            with self.assertRaisesRegex(ValueError, "environment"):
                ac.observer_env(
                    b"TESY_PHASE_FD_TRIGGER=/t\x00TESY_PHASE_FD_TRIGGER=/t", {ac.TRG: "/t"}
                )

    def test_paired_clock_and_reference_work(self):
        def result(price, n=47):
            rows = [
                dict(prefill_s=1, decode_s=1, first_final_s=1, transport_complete_s=1),
                dict(prefill_s=2, decode_s=price, first_final_s=2, transport_complete_s=2),
            ]
            return {
                "arm": {
                    "grade": {
                        "rows": rows,
                        "requests": 2,
                        "model_launches": 1,
                        "trajectories": [78, n],
                    }
                }
            }

        block = {k: result(1) for k in ac.MODES}
        self.assertEqual(family.compare(block, ac.MODES)["T2_ratios_checked"], 12)
        self.assertTrue(family.compare(block | {"ON": result(1.15)}, ac.MODES)["T2_all_in_band"])
        self.assertFalse(
            family.compare(block | {"ON": result(1.15001)}, ac.MODES)["T2_all_in_band"]
        )
        with self.assertRaisesRegex(ValueError, "unequal trajectories"):
            family.compare(block | {"CONTROL": result(1, 46)}, ac.MODES)

    def test_stop_before_successor(self):
        seen = []

        def child(a, out, mode, remaining):
            seen.append(mode)
            if mode == "CONTROL":
                raise ValueError("injected stop")
            return {"arm": {"status": "PREPARED_ONLY", "mode": mode}}

        a = SimpleNamespace(execute=False, prepared=None, prepared_sha256=None)
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(ac, "with_globals", return_value=child),
        ):
            with self.assertRaisesRegex(ValueError, "injected stop"):
                family.family(a, Path(tmp), {"order": list(ac.MODES)})
        self.assertEqual(seen, ["BASE", "CONTROL"])


if __name__ == "__main__":
    unittest.main()
