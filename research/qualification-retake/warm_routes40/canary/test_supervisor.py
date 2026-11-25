"""Verify that a failed independent OFF gate prevents the ON process."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from run import PROFILE, supervisor


class TestHandoff(unittest.TestCase):
    def test_failed_arm_stops_before_next(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            policy = root / "resource-policy.json"
            policy.write_text("{}")
            output = root / "new"
            output.mkdir()
            exe = root / "canary"
            exe.write_text("fixture")
            ids = root / "ids"
            ids.write_text("supplied")
            model = root / "model-fixture"
            model.write_bytes(b"")
            identity = {"size_bytes": 0}
            args = SimpleNamespace(
                new_output_dir=output,
                window=root,
                executable=exe,
                measurement_commit="fixture",
                unit="tesy-mock",
                prepare_only=False,
                backend=root,
            )
            calls = []

            def process(cmd, **_):
                arm = cmd[cmd.index("--run-id") + 1]
                calls.append(arm)
                report = dict(
                    returncode=0,
                    stop_reason=None,
                    maxima={"direct_model_fds": 1, "buffered_model_fds": 0, "swap_bytes": 0},
                    mapped_libraries_match_ldd=True,
                    backend_sha=supervisor.PIN,
                    binary_sha256=supervisor.sha(exe),
                    workload_sha256=supervisor.sha(ids),
                    resource_authority={},
                    cgroup_limit_enforced=True,
                    cgroup_start={"memory_high": PROFILE.cap},
                    cgroup_end={"memory_high": PROFILE.cap},
                    artifact_identity={"stat_at_end": identity, "stat_at_launch": identity},
                    mapped_backend_libraries_sha256={},
                    parallel_runtime={"libraries_sha256": {}},
                )
                (output / "raw" / (arm + ".json")).write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)

            def fail(*_):
                raise ValueError("OFF witness rejected")

            with (
                patch.object(
                    supervisor,
                    "checked",
                    return_value=(model, identity, root, ids, {"libraries_sha256": {}}, {}),
                ),
                patch.object(supervisor, "validate_resource_protocol"),
                patch.object(supervisor, "file_identity", return_value=identity),
                patch.object(supervisor, "IDS", supervisor.sha(ids)),
                patch.object(supervisor, "backend_library_hashes", return_value={}),
                patch.object(supervisor.subprocess, "run", side_effect=process),
                self.assertRaisesRegex(ValueError, "OFF witness rejected"),
            ):
                supervisor.run(args, {"arms": []}, PROFILE, fail)
            self.assertEqual(calls, ["tesy-mock-off"])
            self.assertFalse((output / "tesy-mock-on.json").exists())


if __name__ == "__main__":
    unittest.main()
