import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("c281_pfj", Path(__file__).with_name("profile.py"))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class Conversation(unittest.TestCase):
    def test_trigger_after_success(self):
        with tempfile.TemporaryDirectory() as name:
            d = Path(name)
            t = d / "trigger"
            history = ["T1", M.projected_digest({"fake": 1})]
            M.trigger(t, "ON", 1, d, history)
            self.assertFalse(t.exists())
            (d / "T1-result.json").write_text(
                json.dumps(
                    dict(
                        accepted=True, finish_reason="stop", content_gate="PASS", prefix_gate="PASS"
                    )
                )
            )
            (d / "T2-input.json").write_text("{}")
            with self.assertRaises(ValueError):
                M.trigger(t, "ON", 2, d, history)
            history[1] = M.sha(d / "T2-input.json")
            M.trigger(t, "OFF", 2, d, history)
            self.assertFalse(t.exists())
            M.trigger(t, "ON", 2, d, history)
            self.assertEqual(t.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                M.trigger(t, "ON", 2, d, history)

    def test_changed_trajectory_and_cost_scope(self):
        base = dict.fromkeys(M.METRICS, 10.0)
        self.assertTrue(
            M.paired_cost([base] * 2, [base, base | {"valid_wall_s": 11.5}])["T2_within_band"]
        )
        self.assertFalse(
            M.paired_cost([base] * 2, [base, base | {"prefill_s": 8.49}])["T2_within_band"]
        )
        with self.assertRaises(ValueError):
            M.paired_cost([base] * 2, [base, base | {"prefill_s": float("nan")}])

    def test_incomplete_or_unrelated_off(self):
        args = SimpleNamespace(mode="ON", off_dir=None, off_sha256=None)
        with self.assertRaises(ValueError):
            M.admit_off(args, {})
        args.off_dir = Path("/unused")
        args.off_sha256 = "x"
        for off in (
            {"status": "FAIL_PRESERVED"},
            {"status": "PASS_C281_PFJ_OFF", "gates": {"other": 1}},
        ):
            with patch.object(M, "pinned", return_value=off), self.assertRaises(ValueError):
                M.admit_off(args, {})

    def test_positive_and_negative_price(self):
        phases = dict.fromkeys(
            (
                "compulsory_payload_floor",
                "relaxed_40slot_payload_floor",
                "completed_in_calls_returned_bytes",
                "origin_returned_bytes",
                "returned_after_prefill_for_origin_bytes",
            ),
            1,
        )
        row = dict(prefill_s=11, decode_s=9, first_final_s=20, predicted_n=47)
        value = M.prompt_budget(row, phases)
        m4 = "C281_M4_predicted_tokens"
        ar = "optimistic_AR_post_first_evaluations"
        self.assertEqual(value[m4]["conditional_prompt_budget_ns_upper"], 2166666667)
        gap = (
            value[ar]["conditional_prompt_budget_ns_upper"]
            - value[m4]["conditional_prompt_budget_ns_upper"]
        )
        self.assertLessEqual(abs(6 * gap - 1_000_000_000), 5)
        self.assertEqual(
            M.prompt_budget(row | {"first_final_s": 43}, phases)[m4]["scenario_bytes_at_4_5GBps"], 0
        )
        independent = dict(
            prefill_s=10.784107, decode_s=9.858674, first_final_s=20.385070365, predicted_n=47
        )
        r = M.prompt_budget(independent, phases)
        self.assertEqual(r[m4]["conditional_prompt_budget_ns_upper"], 2_424_377_302)
        self.assertEqual(r[ar]["conditional_prompt_budget_ns_upper"], 2_591_043_969)
        self.assertEqual(r[m4]["denominator"], 47)
        self.assertEqual(r[ar]["denominator"], 46)

    def test_monitor_argv_preserves_server_and_separates_observer(self):
        target = ["/server", "-lv", "3", "--port", "18442"]
        ctl = object.__new__(M.Runtime)
        ctl.reference = {"server_command": target}
        ctl.command = M.capture.diagnostic_args(target)
        ctl.authority = SimpleNamespace(monitor_dir=Path("/fake/monitor"))
        ctl.out = Path("/fake/arm")
        cmd = [
            "systemd-run",
            "-p",
            "MemoryMax=21474836480",
            "--",
            M.sys.executable,
            "-B",
            str(M.post.contract.REPO / "tools/run_bounded.py"),
            "--env",
            "TESY_CPU_WAVE_SKIP_PARKED=1",
            "--",
            *target,
        ]
        for mode in ("OFF", "ON"):
            ctl.native = {
                "LD_LIBRARY_PATH": "/fake/gold",
                "LD_DEBUG": "libs",
                "LD_DEBUG_OUTPUT": "/fake/elf",
            }
            if mode == "ON":
                ctl.native.update(
                    TESY_PHASE_FD_FILE="/private/j", TESY_PHASE_FD_TRIGGER="/private/t"
                )
            changed = ctl.monitor_command(cmd, ctl.out)
            self.assertEqual(changed[-len(ctl.command) :], ctl.command)
            self.assertIn(str(M.INT / "profile/monitor.py"), changed)
            self.assertIn("LimitFSIZE=33554432", changed)
            self.assertEqual("TESY_PHASE_FD_FILE=/private/j" in changed, mode == "ON")
