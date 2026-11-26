"""Model-free checks for short-canary admission and fail-closed arm sequencing."""

import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAMILY = runpy.run_path(str(HERE / "run.py"))
RAW_CASES = FAMILY["ORDER"]


class FamilyTest(unittest.TestCase):
    def test_old_short_numerical_gate_does_not_admit(self):
        earlier = FAMILY["load"](HERE.parent / "nvme_prefix_gate/physical32-e13_5-r2.json")
        for real in earlier["paired_result"]["arms"]:
            with self.assertRaisesRegex(ValueError, "missing common graph"):
                FAMILY["short_coverage"](real)

    def test_wrong_short_group_count(self):
        arm = FAMILY["load"](HERE.parent / "nvme_prefix_gate/physical32-e13_5-r2.json")[
            "paired_result"
        ]["arms"][0]
        arm["numerical"]["common_graph"] = {
            "graphs": 3,
            "rows": 632,
            "logical_ids": 2532,
            "reference_tpr_sha256": FAMILY["REF_ROUTES"],
        }
        with self.assertRaisesRegex(ValueError, "short numerical"):
            FAMILY["short_coverage"](arm)

    def test_arm_plan(self):
        a = SimpleNamespace(backend=Path("/fixture/backend"), executable=Path("/fixture/client"))
        for case, mode in RAW_CASES:
            cmd = FAMILY["command"](
                a,
                "tesy-fixture",
                case,
                mode,
                Path("/fixture/model"),
                Path("/fixture/ids"),
                Path("/fixture/raw/native"),
                Path("/fixture/locked"),
            )
            explicit = [cmd[i + 1] for i, item in enumerate(cmd) if item == "--env"]
            self.assertIn("TESY_ROUTE_GRAPH_WITNESS=1", explicit)
            self.assertEqual("TESY_PREFIX_ROUTE_AUDIT=1" in explicit, mode == "ON")
            self.assertNotIn("TESY_C294_WINDOW", " ".join(cmd))
            self.assertEqual(
                cmd[-7:],
                [
                    "/fixture/client",
                    "/fixture/model",
                    "/fixture/ids",
                    case,
                    "/fixture/raw/native",
                    "R0",
                    "v1",
                ],
            )
            self.assertIn("LimitFSIZE=33554432", cmd)
            self.assertIn("--collect-start-inventory", cmd)

    def test_first_failure_blocks_other_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "fixture"
            exe.write_bytes(b"fault fixture only")
            a = SimpleNamespace(backend=root, executable=exe, execute=True, unit="tesy-test")
            result = {"arms": []}
            resources = FAMILY["load"](
                FAMILY["ROOT"] / "results/c294-feature-ready-service-window-20261006/protocol.json"
            )["resources"]
            sha = FAMILY["sha256"](exe)
            plan = {
                "resources": resources,
                "limits": {},
                "model_stat": FAMILY["host"].file_identity(exe),
                "executable_sha256": sha,
            }
            FAMILY["host"].publish(root / "protocol.json", plan)
            with patch.dict(
                FAMILY["run"].__globals__,
                prepare=lambda *_: (exe, exe, {}, {}, plan),
                FIXTURE=sha,
                measure=lambda *_: 1,
            ):
                with self.assertRaisesRegex(ValueError, "arm incomplete"):
                    FAMILY["run"](a, root, result)
            self.assertEqual(
                [(r["case"], r["mode"], r["status"]) for r in result["arms"]],
                [("nominal153", "OFF", "FAIL_PRESERVED")],
            )
            self.assertFalse(list(root.rglob("*.launch.json")))


if __name__ == "__main__":
    unittest.main()
