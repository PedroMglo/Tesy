import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runner


class ScopeTests(unittest.TestCase):
    def test_unified_membership(self):
        root = Path("/sys/fs/cgroup")
        unit = "tesy-tiny-01.scope"
        self.assertEqual(
            runner.scope_at(unit, "0::/user.slice/" + unit, root), root / "user.slice" / unit
        )
        for path in (
            "1:cpu:/user.slice/" + unit,
            "0::/else.scope",
            "0::/../" + unit,
            "0::/a/" + unit + "\n0::/b/" + unit,
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.scope_at(unit, path, root)

    def test_boundaries_and_oom(self):
        with tempfile.TemporaryDirectory() as d:
            cg = Path(d)
            fields = {
                "memory.max": runner.RESIDENT,
                "memory.swap.max": 0,
                "memory.peak": 19000,
                "memory.current": 12000,
                "memory.swap.current": 0,
                "cgroup.procs": os.getpid(),
                "memory.events": "low 0\nhigh 0\nmax 3\noom 0\noom_kill 0\noom_group_kill 0\n",
            }
            for k, v in fields.items():
                (cg / k).write_text(str(v))
            data = runner.snapshot(cg)
            runner.validate(data)
            for key, value in (
                ("sole_process", False),
                ("memory.max", runner.RESIDENT + 1),
                ("memory.swap.max", 1),
                ("memory.swap.current", 1),
                ("memory.peak", runner.RESIDENT + 1),
            ):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    runner.validate({**data, key: value})
            for key in ("oom", "oom_kill", "oom_group_kill"):
                for value in (1, None):
                    events = data["memory.events"].copy()
                    if value is None:
                        del events[key]
                    else:
                        events[key] = value
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        runner.validate({**data, "memory.events": events})

    def test_cap_in_probe_subprocess_only(self):
        child = subprocess.check_output(
            [
                sys.executable,
                "-B",
                "-c",
                "import runner,resource as r;runner.child_limits();print(r.getrlimit(r.RLIMIT_AS))",
            ],
            cwd=runner.HERE,
            text=True,
        )
        self.assertEqual(child.strip(), str((runner.ADDRESS, runner.ADDRESS)))

    def test_signal_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = root / "new"
            args = [
                "runner",
                "--stock-build-root",
                str(root / "stock"),
                "--overlay-root",
                str(root / "overlay"),
                "--new-output-dir",
                str(out),
                "--scope-unit",
                "tesy-test.scope",
            ]

            def stop(*_):
                os.kill(os.getpid(), signal.SIGTERM)

            # main is the entry point of a single-use process; restore process-local
            # settings after this test runs it in the unit test interpreter.
            signals = {
                s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)
            }
            try:
                with (
                    patch.object(sys, "argv", args),
                    patch.dict(os.environ),
                    patch.object(runner, "execute", stop),
                ):
                    self.assertEqual(runner.main(), 1)
            finally:
                for s, old in signals.items():
                    signal.signal(s, old)
            r = json.loads((out / "receipt.json").read_text())
            self.assertEqual(r["status"], "FAIL_PRESERVED")
            self.assertIn("SIGTERM", r["error"])
            self.assertEqual(r["child_rlimit_as_bytes"], runner.ADDRESS)
            with patch.object(sys, "argv", args), self.assertRaises(FileExistsError):
                runner.main()


if __name__ == "__main__":
    unittest.main()
