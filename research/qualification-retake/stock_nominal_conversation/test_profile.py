"""Test the C281 geometry, identity and stop paths without a server or any model."""

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stock_nominal_controller", HERE / "profile.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class MockProbe:
    timeout_s = 300
    run_id = "stock-nominal-e20-c281"
    pass_status = "PASS_STOCK_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
    protocol_path = HERE / "protocol.md"
    ram_profile = "R0_E20"


class Tests(unittest.TestCase):
    def test_geometry_marks_exactly_one_example_and_date(self):
        template = "init: chat template, example_format: 'text\nCurrent date: {}\nend'\n"
        good = template.format(p.DATE)
        self.assertTrue(p.geometry(good)["dated_init_example"])
        self.assertFalse(p.full.geometry(good)["dated_init_example"])
        for wrong in [
            template.format("2026-09-29"),
            good + good,
            good.replace(p.DATE, p.DATE + "\nCurrent date: 2026-10-05"),
        ]:
            self.assertFalse(p.geometry(wrong)["dated_init_example"])

    def test_effective_template_is_bound_to_the_final_argv(self):
        prefix = ["server", "-m", "model", "-lv", "4"]
        original = [
            "--swa-full",
            "--jinja",
            "--chat-template-file",
            "sample",
            "--chat-template-kwargs",
            p.full.KWARGS,
        ]
        args, observed = p.date_arguments(original, prefix)
        self.assertEqual(json.loads(args[-1]), {"tesy_template_date": "2026-10-05"})
        self.assertEqual(original[-1], p.full.KWARGS)
        self.assertEqual(
            observed, hashlib.sha256(b"\0".join(os.fsencode(x) for x in prefix + args)).hexdigest()
        )
        with self.assertRaisesRegex(ValueError, "count"):
            p.date_arguments(original + original, prefix)

    def test_C55_follows_original_local_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            family = Path(d) / "family"
            inputs = Path(d) / "input"
            family.write_bytes(
                (HERE.parent / "stock_server_logits/family-r2/receipt.json").read_bytes()
            )
            inputs.write_bytes(
                (HERE.parent / "nominal_stock_input/evidence-r01/receipt.json").read_bytes()
            )
            first = p.datetime(2026, 11, 25, 5, tzinfo=p.UTC)
            stamp = int(first.timestamp()) - 1
            os.utime(family, (stamp, stamp))
            os.utime(inputs, (stamp, stamp))
            a = SimpleNamespace(family_receipt=family, input_receipt=inputs)
            self.assertEqual(p.validate_gates(a, first.isoformat())["physical_B20_sha256"], p.B20)
            with self.assertRaisesRegex(ValueError, "precedes"):
                p.validate_gates(a, (first - timedelta(seconds=2)).isoformat())
            family.write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "identity"):
                p.validate_gates(a, first.isoformat())

    def test_observer_absence_and_runtime_mode(self):
        env = b"TESY_STOCK_LAZY_MMAP=1\0LD_LIBRARY_PATH=/private:/stock\0"
        maps = "100-200 r-xp 0 00:1 1 /private/libllama.so.0\n"
        p.check_environment(env, maps, "/private:/stock")
        for bad in [
            env + b"LD_PRELOAD=/some/lib.so\0",
            env + b"TESY_F32_PROFILE=stock120b\0",
            env.replace(b"=1", b"=0"),
        ]:
            with self.assertRaisesRegex(ValueError, "observer"):
                p.check_environment(bad, maps, "/private:/stock")
        with self.assertRaisesRegex(ValueError, "observer"):
            p.check_environment(
                env, maps.replace("libllama.so.0", "observer.so (deleted)"), "/private:/stock"
            )

    def test_turn_watchdog_and_censor_without_a_finished_response(self):
        profile = p.Profile(MockProbe)
        self.assertEqual(profile.paging_cap_bytes, 20 * p.core.GIB)
        guard = p.Experiment(*([None] * 7))
        guard.profile = profile
        for turn, cap in ((1, 180), (2, 90)):
            data = {
                "phase": "chat",
                "turn": turn,
                "completed_turns": turn - 1,
                "send_monotonic_s": 42,
                "deadline_monotonic_s": 42 + cap,
                "first_final_s": None,
            }
            profile.progress["product_progress"] = data
            with (
                patch.object(p.lazy.Experiment, "watch"),
                patch.object(p.time, "monotonic", return_value=42 + cap),
            ):
                with self.assertRaisesRegex(ValueError, f"T{turn}_REQUEST_TIMEOUT"):
                    guard.watch()
                record = {"status": "FAIL", "reason": "original_stop"}
                profile.close(record)
            self.assertEqual(record["reason"], "original_stop")
            self.assertTrue(record["interrupted_product"]["open_exchange_without_completion"])
            self.assertEqual(record["interrupted_product"]["elapsed_since_open_request_s"], cap)
            self.assertEqual(
                record["interrupted_product"]["next_turn_not_run"], 2 if turn == 1 else None
            )

    def test_window_reserves_time_for_inputs_and_both_natural_turns(self):
        profile = p.Profile(MockProbe)
        guard = p.Experiment(*([None] * 7))
        guard.profile = profile
        with (
            patch.object(p, "datetime") as utc,
            patch.object(p.time, "monotonic", return_value=profile.start_clock),
        ):
            utc.now.return_value = p.END - timedelta(seconds=551)
            guard.require_window(250)
            utc.now.return_value = p.END - timedelta(seconds=550)
            with self.assertRaisesRegex(ValueError, "unit_clock"):
                guard.require_window(250)


if __name__ == "__main__":
    unittest.main()
