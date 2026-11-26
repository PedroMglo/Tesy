import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_profile():
    source = Path(__file__).resolve().with_name("profile.py")
    spec = importlib.util.spec_from_file_location("b3_pair_profile", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


p = load_profile()


class TestTwoArm(unittest.TestCase):
    def test_derives_only_the_contrast_and_private_limits(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = root / "capture"
            old.touch()
            raw = root / "tesy-test.capture"
            cmd = [
                "systemd-run",
                "LimitFSIZE=8388608",
                "--",
                "monitor",
                "--variant",
                "C270",
                "--resource-protocol",
                "orig",
                "--",
                str(old),
                "model",
                "ids",
                str(raw),
                "--ngl",
                "12",
            ]
            result = p.derivative_command(
                cmd, old, root / "new", root / "gold", "AR", "tesy-test", root / "protocol"
            )
            self.assertEqual(
                result[-6:], [str(root / "new"), "model", "ids", str(root / "gold"), "AR", str(raw)]
            )
            self.assertIn("LimitFSIZE=41943040", result)
            with self.assertRaises(ValueError):
                p.derivative_command(
                    cmd, old, root / "new", root / "gold", "wrong", "tesy-test", root / "protocol"
                )

    def test_state_must_match_before_logit_comparison(self):
        a = {
            "prefix": 123,
            "states": {"initial-kv.bin": 1, "initial-pool.bin": 2, "post3-kv.bin": 3},
        }
        with patch.object(
            p.logits_grade, "compare_rows", return_value={"bitwise": False, "same_greedy": True}
        ) as compare:
            b = {"prefix": 123, "states": dict(a["states"], **{"initial-kv.bin": 7})}
            with self.assertRaises(ValueError):
                p.compare_pair(Path("."), Path("."), a, b)
            compare.assert_not_called()
            r = p.compare_pair(Path("."), Path("."), a, a)
            self.assertFalse(r["all_four_bitwise"])
            self.assertTrue(r["all_four_unique_greedy_equal"])
            self.assertEqual(r["first_unequal_logit_row"], "decode0")
            self.assertEqual(compare.call_count, 4)

    def test_post_full_block_state_is_additional(self):
        a = {
            "prefix": 123,
            "states": {"initial-kv.bin": 1, "initial-pool.bin": 2, "post3-kv.bin": 3},
        }
        b = {"prefix": 123, "states": dict(a["states"], **{"post3-kv.bin": 4})}
        with patch.object(
            p.logits_grade, "compare_rows", return_value={"bitwise": True, "same_greedy": True}
        ):
            r = p.compare_pair(Path("."), Path("."), a, b)
            self.assertEqual(r["status"], "DIFFERENT_LOGIT_BITS_OR_CARRY_STATE")
            self.assertTrue(r["all_four_bitwise"])
            self.assertFalse(r["post3_kv_equal"])
