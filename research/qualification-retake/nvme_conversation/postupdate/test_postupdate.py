import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "tesy_c281_driver", Path(__file__).with_name("profile.py")
)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class Postupdate(unittest.TestCase):
    def test_legacy_projection_changes_only_cuda_location(self):
        gpu = dict(path="/private/CUDA", sha256="a")
        other = dict(path="/bin/l", sha256="b")
        original = dict(dso={"libcuda.so.1": gpu, "libllama.so": other}, command=["old"])
        before = copy.deepcopy(original)
        projected = profile.projection(original)
        self.assertEqual(
            projected["dso"]["libcuda.so.1"], dict(path=profile.PREVIOUS_CUDA, sha256="a")
        )
        self.assertEqual(projected["dso"]["libllama.so"], other)
        self.assertEqual(original, before)

    def test_scope_and_native_are_isolated_and_server_tail_is_identical(self):
        exe = sys.executable
        native = {
            "LD_DEBUG": "libs",
            "LD_LIBRARY_PATH": "/ggml:/srv:/driver",
            "LD_DEBUG_OUTPUT": "/raw/loader",
        }
        frozen = [
            "systemd-run",
            "--",
            exe,
            "-B",
            str(profile.contract.REPO / "tools/run_bounded.py"),
            "--env",
            "TESY_CPU_WAVE_SKIP_PARKED=1",
            "--",
            "/server",
            "--n-ubatch",
            "32",
        ]
        cmd = profile.monitor_argv(frozen, Path("/nvml"), native)
        self.assertEqual(cmd[cmd.index("/server") :], frozen[frozen.index("/server") :])
        self.assertIn("LD_LIBRARY_PATH=/nvml", cmd[: cmd.index(exe)])
        self.assertIn("LD_LIBRARY_PATH=/ggml:/srv:/driver", cmd[cmd.index(exe) :])
        self.assertNotIn("LD_LIBRARY_PATH=/nvml", cmd[cmd.index(exe) :])
        with self.assertRaises(ValueError):
            profile.monitor_argv(frozen, Path("/nvml"), native | {"LD_PRELOAD": "/foreign"})

    def test_c270_proof_and_refusals(self):
        with tempfile.TemporaryDirectory() as loc:
            root = Path(loc)
            raw = root / "raw"
            raw.mkdir()
            unit = "tesy-c270-test"
            grade = dict(
                status="PASS_PRIVATE_R0_SELECTED_BRIDGE",
                core_payloads=1500,
                full_logits=5,
                prospective_witness=dict(
                    status="PASS_PROSPECTIVE_WITNESS", combinations=166, components=996
                ),
            )

            def write(path, obj):
                path.write_text(json.dumps(obj))
                return profile.sha256(path)

            driver = [
                "libcuda.so.1",
                "libnvidia-ptxjitcompiler.so.1",
                "libnvidia-nvvm70.so.4",
                "libnvidia-gpucomp.so.620.70.06",
            ]
            policy = write(root / "resource-policy.json", {})
            proto = dict(
                envelope="E20_R0",
                execution_scope_unit=unit,
                start_inventory={"policy_sha256": policy},
                pinned={"server_sha256": "server"},
            )
            psha = write(root / "protocol.json", proto)
            qual = dict(
                kernel={"release": "k"},
                driver_deployment="d",
                preflight_sha256="pre",
                static_map_sha256="map",
                base_protocol_sha256=psha,
                native_explicit_env={"LD_DEBUG_OUTPUT": str(raw / "loader")},
            )
            (raw / "loader.11").write_bytes(b"loader")
            auth = dict(
                status="PASS_LIVE_AND_LOADER_C270",
                static_map_sha256="map",
                kernel=qual["kernel"],
                deployment_commit="d",
                live_samples=3,
                native_pid=11,
                loader_sha256=hashlib.sha256(b"loader").hexdigest(),
                driver_providers={k: dict(requested=True, initialized=True) for k in driver}
                | {"libnvcuextend.so.620.70.06": dict(requested=True, initialized=False)},
            )
            summary = dict(
                envelope="E20_R0",
                capture_sha256="capture",
                protocol_sha256=psha,
                qualified_protocol_sha256=write(root / "qualified-protocol.json", qual),
                selected_sha256=write(root / "selected.json", grade),
                numerical_gate=grade,
                authority=auth,
                preflight_sha256="pre",
                monitor_sha256=write(
                    raw / (unit + ".json"),
                    dict(returncode=0, stop_reason=None, mapped_libraries_match_ldd=True),
                ),
                launch_sha256=write(
                    raw / (unit + ".launch.json"), {"process_identity": {"pid": 11}}
                ),
            )
            args = SimpleNamespace(c270=root / "receipt.json", preflight_sha256="pre")
            pre = dict(
                static_map_sha256="map",
                kernel=qual["kernel"],
                deployment_commit="d",
                native_alias_sha256=dict.fromkeys(driver),
                arms={
                    "C270": {"executable_sha256": "capture"},
                    "C281": {"executable_sha256": "server"},
                },
            )

            def check(obj):
                args.c270_sha256 = write(args.c270, obj)
                return profile.c270_evidence(
                    args, proto, args.c270_sha256, pre, {"arms": pre["arms"]}
                )

            self.assertEqual(check(summary)["c270_authority"], auth["status"])
            for mutation in (
                dict(envelope="E18_DIAGNOSTIC_ONLY"),
                dict(preflight_sha256="other"),
                dict(authority=auth | dict(live_samples=0)),
                dict(monitor_sha256="foreign"),
            ):
                with self.assertRaises(ValueError):
                    check(summary | mutation)
            (raw / "loader.11").write_bytes(b"foreign")
            with self.assertRaises(ValueError):
                check(summary)

    def test_missing_startup_vma_rejected_and_foreign_pid_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = profile.Runtime.__new__(profile.Runtime)
            runtime.authority = SimpleNamespace(
                initial={"a", "b"}, live=lambda _: {"a"}, recheck=lambda: None
            )
            runtime.seen = set()
            runtime.out = Path(temp)
            runtime.pid = None
            with self.assertRaises(ValueError):
                runtime.first(7)
            self.assertFalse((runtime.out / "first-client-map.json").exists())
            runtime.pid = 9
            with self.assertRaises(ValueError):
                runtime.first(7)


if __name__ == "__main__":
    unittest.main()
