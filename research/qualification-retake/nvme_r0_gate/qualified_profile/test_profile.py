import profile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import authority


class Qualified(unittest.TestCase):
    def test_distinct_monitor_and_child_search(self):
        base = [
            "systemd-run",
            "--",
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            "LC_ALL=C",
            "HOME=/tmp",
            "python3",
            "monitor",
            "--env",
            "TESY_CPU_WAVE_SKIP_PARKED=1",
            "--",
            "capture",
            "x.gguf",
            "ids",
            "out",
            "--ngl",
            "12",
        ]
        child = {
            "LD_LIBRARY_PATH": "libs:driver",
            "LD_DEBUG": "libs",
            "LD_DEBUG_OUTPUT": "/raw/loader",
        }
        cmd = profile.qualified_command(base, "monitor-nvml", child)
        self.assertEqual(cmd[-6:], base[-6:])
        self.assertTrue("LD_LIBRARY_PATH=monitor-nvml" in cmd[: cmd.index("python3")])
        self.assertNotIn("LD_LIBRARY_PATH=libs:driver", cmd[: cmd.index("python3")])
        self.assertEqual(
            [cmd[i + 1] for i, item in enumerate(cmd) if item == "--env"],
            ["TESY_CPU_WAVE_SKIP_PARKED=1", *[k + "=" + v for k, v in child.items()]],
        )
        self.assertNotIn("LD_LIBRARY_PATH=monitor-nvml", base)

    def test_explicit_environment_requires_identity_and_no_preload(self):
        exact = {
            "TESY_CPU_WAVE_SKIP_PARKED": "1",
            "LD_LIBRARY_PATH": "a:b",
            "LD_DEBUG": "libs",
            "LD_DEBUG_OUTPUT": "/x",
        }
        m = {"explicit_env": exact.copy(), "relevant_environment": {"LD_LIBRARY_PATH": "a:b"}}
        original = mock.Mock()
        profile.check_native_manifest(m, {}, {}, exact, original)
        self.assertIs(original.check_monitor.call_args.args[0], m)
        self.assertEqual(
            original.check_monitor.call_args.kwargs["loader_env"],
            {k: v for k, v in exact.items() if k.startswith("LD_")},
        )
        self.assertEqual(m["explicit_env"], exact)
        for key, value in (
            ("explicit_env", exact | {"FOO": "bar"}),
            ("relevant_environment", {"LD_LIBRARY_PATH": "a:b", "LD_PRELOAD": "x"}),
        ):
            with self.assertRaises(ValueError):
                profile.check_native_manifest(m | {key: value}, {}, {}, exact, original)

    def test_partial_launch_never_yields_a_pid(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "launch"
            self.assertIsNone(profile.completed_launch(path))
            path.write_text('{"pid":')
            self.assertIsNone(profile.completed_launch(path))
            path.write_text('{"pid":41}\n')
            self.assertEqual(profile.completed_launch(path), {"pid": 41})

    def test_alias_gates(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "aliases"
            root.mkdir()
            elf = base / "a"
            elf.write_bytes(b"1")
            link = root / "driver"
            link.symlink_to(elf)
            authority.aliases(root, {"driver": str(elf)})
            with self.assertRaises(ValueError):
                authority.aliases(root, {"driver": str(base / "fake")})
            (root / "nvml").symlink_to(elf)
            with self.assertRaises(ValueError):
                authority.aliases(root, {"driver": str(elf)})

    def test_positive_vma_and_mutated_device_inode_unknown_and_unlink(self):
        with tempfile.TemporaryDirectory() as d:
            path = (Path(d) / "libsynthetic.so.1").resolve()
            path.write_bytes(bytes(4096))
            info = authority.identity(path)
            name = str(path)
            key = authority.reference_key(name, info)
            prefix = f"123-456 r-xp 00000000 {key[0]:02x}:{key[1]:02x} {key[2]} "
            line = prefix + name
            self.assertEqual(authority.check_maps(line, {name}, {name: key}), {name})
            for mutated in ((key[0], key[1] + 1, key[2]), (key[0], key[1], key[2] + 1)):
                with self.assertRaises(ValueError):
                    authority.check_maps(line, {name}, {name: mutated})
            for altered in (line + " (deleted)",):
                with self.assertRaises(ValueError):
                    authority.check_maps(altered, {name}, {name: key})
            with self.assertRaises(ValueError):
                authority.check_maps(line, set(), {})

    def test_wrong_pid_is_rejected_in_complete_real_loader_format(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log"
            path = Path(d) / "log.17"
            path.write_text("16: harmless control\n17: calling init: /x\n")
            a = authority.Authority.__new__(authority.Authority)
            a.recheck = lambda: None
            a.loader = SimpleNamespace(initialized=lambda *_: {"/x"})
            a.origin = SimpleNamespace(all_requests=lambda *_: set())
            with self.assertRaisesRegex(ValueError, "foreign loader journal PID"):
                a.audit(p, 17)
            Path(d, "log.20").write_text("")
            with self.assertRaisesRegex(ValueError, "cardinality"):
                a.audit(p, 17)
