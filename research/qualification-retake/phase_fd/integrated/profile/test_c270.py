import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c270


class C270Checks(unittest.TestCase):
    def test_environment_remains_separate(self):
        d = Path("/new")
        old = "/original"
        new = "/candidate:/original"
        native = ["capture", "target.gguf", "ids.tsv", "out", "--ngl", "12"]
        start = [
            "systemd-run",
            "LimitFSIZE=8388608",
            "--",
            "/usr/bin/env",
            "-i",
            "LD_LIBRARY_PATH=/monitor",
            "/usr/bin/python3",
            "-B",
            str(c270.REPO / "tools/run_bounded.py"),
            "--resource-protocol",
            "/new/protocol.json",
            "--variant",
            "C269-R0-selected189+32-E20_R0",
            "--env",
            "TESY_CPU_WAVE_SKIP_PARKED=1",
            "--env",
            "LD_LIBRARY_PATH=/original",
            "--",
            *native,
        ]
        for mode in ("ON", "OFF"):
            cmd = c270.adjust_command(start, old, new, d, mode)
            self.assertEqual(cmd[-6:], native)
            self.assertEqual(cmd.count("LD_LIBRARY_PATH=/monitor"), 1)
            self.assertEqual(("TESY_PHASE_FD_FILE=/new/raw/phase.pfj1" in cmd), mode == "ON")
            self.assertEqual(cmd.count("LD_LIBRARY_PATH=" + new), 1)
            self.assertNotIn("LD_PRELOAD=", " ".join(cmd))
        with self.assertRaises(ValueError):
            c270.adjust_command(start + ["LimitFSIZE=8388608"], old, new, d, "ON")

    def test_validate_full_record_before_single_projection(self):
        exp = {
            "TESY_CPU_WAVE_SKIP_PARKED": "1",
            "TESY_PHASE_FD_FILE": "/new/file",
            "LD_LIBRARY_PATH": "/new:/old",
            "LD_DEBUG": "libs",
            "LD_DEBUG_OUTPUT": "/out/ld",
        }
        effective = {k: v for k, v in exp.items() if not k.startswith("LD_DEBUG")}
        rec = {"explicit_env": dict(exp), "relevant_environment": effective}
        projections = []
        control = SimpleNamespace(
            check_monitor=lambda m, *args, **kwargs: projections.append(m["explicit_env"])
        )
        c270.monitor_result(rec, {"pinned": {}}, exp, control)
        self.assertNotIn("TESY_PHASE_FD_FILE", projections[0])
        self.assertIn("TESY_PHASE_FD_FILE", rec["explicit_env"])
        for k, v in [
            ("TESY_PHASE_FD_TRIGGER", "/wrong"),
            ("TESY_PHASE_FD_FILE", "/different"),
            ("LD_PRELOAD", "/bad"),
        ]:
            with self.assertRaises(ValueError):
                c270.monitor_result(
                    dict(rec, relevant_environment=effective | {k: v}), {"pinned": {}}, exp, control
                )
        off = {k: v for k, v in exp.items() if k != "TESY_PHASE_FD_FILE"}
        with self.assertRaises(ValueError):
            c270.monitor_result(dict(rec, explicit_env=off), {"pinned": {}}, off, control)

    def test_geometry_and_conservation_are_jointly_required(self):
        calls = [dict(tokens=189, tiles=[32] * 5 + [29], positions=[0, 188])] + [
            dict(tokens=1, tiles=[1], positions=[i, i]) for i in range(189, 221)
        ]
        grade = {"status": "PASS", "calls": calls}
        c270.require_journal(grade)
        for bad in [
            dict(grade, status="FAIL"),
            dict(grade, calls=calls[:-1]),
            dict(grade, calls=[dict(calls[0], tiles=[189]), *calls[1:]]),
            dict(grade, calls=[dict(calls[0], positions=[0, 189]), *calls[1:]]),
        ]:
            with self.assertRaises(ValueError):
                c270.require_journal(bad)
