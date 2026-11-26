import json
import tempfile
import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
family = run_path(HERE / "family.py")["family"]
compare = run_path(HERE / "compact.py")["compare"]


class FamilyTests(unittest.TestCase):
    def test_failure_of_second_arm_prevents_third(self):
        with tempfile.TemporaryDirectory() as tmp:
            call = Mock(side_effect=[{"sha256": "disposable"}, ValueError("O not admitted")])
            with patch.dict(family.__globals__, call_child=call):
                with self.assertRaisesRegex(ValueError, "O not admitted"):
                    family(SimpleNamespace(execute=False, order="ROP"), Path(tmp), {"order": "ROP"})
            self.assertEqual([c.args[2] for c in call.call_args_list], ["R", "O"])

    def test_preflight_from_other_checkout_cannot_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "family.json"
            p.write_text(
                json.dumps({"status": "PASS_ROP_PREFLIGHT", "identity": {"commit": "old"}})
            )
            with patch.dict(family.__globals__, call_child=Mock(side_effect=AssertionError)):
                with self.assertRaisesRegex(ValueError, "changed preflight"):
                    family(
                        SimpleNamespace(execute=True, prepared=p, order="ROP"),
                        root,
                        {"commit": "new", "order": "ROP"},
                    )

    def run_simulated_block(self, base, prepare_order, run_order, failure=None):
        pre = base / "prepared"
        pre.mkdir()
        out = base / "physical"
        out.mkdir()
        calls = []
        identity = dict(order=prepare_order)

        def child(args, directory, mode, timeout):
            calls.append(("start" if args.execute else "prepare", mode))
            if args.execute and failure == ("start", mode):
                raise ValueError("arm failure")
            dest = directory / mode
            dest.mkdir()
            payload = dest / "arm.json"
            payload.write_text(json.dumps(dict(mode=mode, execute=args.execute)))
            return {"sha256": family.__globals__["sha"](payload)}

        def wait(directory, unit_prefix, previous):
            calls.append(("closed", previous))
            if failure == ("closed", previous):
                raise TimeoutError("unavailable port")
            return 1.25

        with patch.dict(family.__globals__, call_child=child, await_closed_endpoint=wait):
            prep = family(SimpleNamespace(execute=False, order=prepare_order), pre, identity)
            prerec = pre / "family.json"
            prerec.write_text(json.dumps(prep))
            try:
                result = family(
                    SimpleNamespace(
                        execute=True, order=run_order, prepared=prerec, unit_prefix="test"
                    ),
                    out,
                    dict(order=run_order),
                )
            except (ValueError, TimeoutError) as exc:
                return None, calls, str(exc)
        return result, calls, None

    def test_inverted_block_checks_actual_predecessors_before_each_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, calls, error = self.run_simulated_block(Path(tmp), "POR", "POR")
        self.assertIsNone(error)
        self.assertEqual(
            calls,
            [
                ("prepare", "P"),
                ("prepare", "O"),
                ("prepare", "R"),
                ("start", "P"),
                ("closed", "P"),
                ("start", "O"),
                ("closed", "O"),
                ("start", "R"),
            ],
        )
        self.assertEqual(result["order"], "POR")
        self.assertEqual(result["closed_endpoint_wait_before_arm_s"], {"O": 1.25, "R": 1.25})

    def test_changed_order_never_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, calls, error = self.run_simulated_block(Path(tmp), "ROP", "POR")
        self.assertIn("changed preflight", error)
        self.assertFalse(any(action in ("start", "closed") for action, _ in calls))

    def test_failure_of_first_second_or_wait_stops_inverted_block(self):
        for failure, starts in (
            (("start", "P"), ["P"]),
            (("start", "O"), ["P", "O"]),
            (("closed", "P"), ["P"]),
            (("closed", "O"), ["P", "O"]),
        ):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                _, calls, error = self.run_simulated_block(Path(tmp), "POR", "POR", failure)
                self.assertTrue(error)
                self.assertEqual([m for action, m in calls if action == "start"], starts)

    def test_different_component_signs_are_kept(self):
        fast = dict(
            first_final_s=8,
            transport_complete_s=9,
            validated_terminal_s=9,
            prefill_s=2,
            decode_s=5,
            decode_tok_s=6,
        )
        other = fast | {"first_final_s": 9, "prefill_s": 1, "decode_s": 7, "decode_tok_s": 4}
        result = compare({"rows": [fast, fast]}, {"rows": [other, other]})["T2"]
        self.assertEqual(result["first_final_s"]["seconds_saved"], -1)
        self.assertEqual(result["prefill_s"]["seconds_saved"], 1)
        self.assertEqual(result["decode_tok_s_delta"], -2)


if __name__ == "__main__":
    unittest.main()
