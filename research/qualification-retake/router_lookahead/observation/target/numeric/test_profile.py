import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import patch

S = run_path(str(Path(__file__).with_name("profile.py")))


class ProfileTest(unittest.TestCase):
    def test_explicit_mode_on_same_store(self):
        for active in [False, True]:
            with patch.object(S["base"], "command", return_value=["--env", "a=b", "--", "exe"]):
                cmd = S["Capture"].command(None, SimpleNamespace(probe=active))
            self.assertEqual(cmd.count(S["FLAG"] + "=1"), int(active))
            self.assertEqual(cmd[-2:], ["--", "exe"])

    def test_monitor_proves_env_before_old_validator(self):
        for active in [False, True]:
            env = {S["FLAG"]: "1"} if active else {}
            monitor = {"explicit_env": dict(env), "relevant_environment": dict(env)}
            with patch.object(S["base"], "validate_monitor") as validate:
                S["Capture"].validate_monitor(monitor, env, {})
                self.assertEqual(validate.call_args.args[1], {})
                monitor["relevant_environment"][S["FLAG"]] = "0"
                with self.assertRaises(ValueError):
                    S["Capture"].validate_monitor(monitor, env, {})
