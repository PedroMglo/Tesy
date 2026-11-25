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
                    family(SimpleNamespace(execute=False), Path(tmp), {})
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
                    family(SimpleNamespace(execute=True, prepared=p), root, {"commit": "new"})

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
