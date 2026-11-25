import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location("new_native_" + name, HERE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


capture = module("profile")
b3 = module("b3")


class CaptureTests(unittest.TestCase):
    def test_native_option_appended_after_original(self):
        args = ["/server", "--port", "18442", "-lv", "3", "--no-warmup"]
        self.assertEqual(capture.diagnostic_args(args), [*args, "--log-verbosity", "5"])
        for altered in (
            args + ["--verbosity", "3"],
            args[:4] + ["5"],
            args[:2] + ["18443"] + args[3:],
        ):
            with self.assertRaises(ValueError):
                capture.diagnostic_args(altered)

    def test_exact_native_argv(self):
        rt = capture.Runtime.__new__(capture.Runtime)
        rt.command = ["/server", "--arg", "one two"]
        with patch.object(Path, "read_bytes", return_value=b"/server\0--arg\0one\0two\0"):
            with self.assertRaises(ValueError):
                rt.check_live_command(1)
        self.assertEqual(capture.argv_image(rt.command), b"/server\0--arg\0one two\0")

    def test_aggregate_after_monitor_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder)
            (raw / "stderr").write_bytes(b"AA")
            (raw / "final-monitor").write_bytes(b"BB")
            self.assertEqual(capture.final_raw_bytes(raw, 4), 4)
            with self.assertRaises(ValueError):
                capture.final_raw_bytes(raw, 3)
            (raw / "alias").symlink_to(raw / "stderr")
            with self.assertRaises(ValueError):
                capture.final_raw_bytes(raw, 20)

    def test_historical_costs_and_denominators(self):
        row = dict(outputs=46, ordinary=23, proposals=11, calls=34)
        result = b3.limits(row, 9.858674, True)
        self.assertAlmostEqual(result["maximum_ratio_b3_per_ar_for_15pct_less_decode"], 1.46363636)
        self.assertAlmostEqual(
            result["maximum_ratio_b3_per_ar_for_6tps"], (47 / 6 / (9.858674 / 46) - 23) / 11
        )
        self.assertGreater(result["coordination_budget_seconds_6tps_if_b3_costs_one_ar"], 0)
        with self.assertRaises(ValueError):
            b3.limits(dict(outputs=32, ordinary=19, proposals=7, calls=26), 9.858674, True)

    def test_no_proposals_and_no_future(self):
        result = b3.limits(dict(outputs=46, ordinary=46, proposals=0, calls=46), 9.858674, True)
        self.assertIsNone(result["maximum_ratio_b3_per_ar_for_6tps"])
        self.assertFalse(result["free_overhead_b3_equal_to_ar_reaches_6tps"])
        self.assertLess(result["coordination_budget_seconds_6tps_if_b3_costs_one_ar"], 0)
