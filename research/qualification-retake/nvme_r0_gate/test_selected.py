import copy
import unittest
from pathlib import Path

from measure import check_gate, check_monitor
from prepare import BASE, CAPS, admit, file_identity, load, validate_resource_protocol


class SelectedGateTest(unittest.TestCase):
    def test_e18_does_not_admit_e20_or_other_failures(self):
        m = {"cap_max_bytes": CAPS["E18_DIAGNOSTIC_ONLY"]}
        p = {"memory": m}
        w = {
            "status": "NOT_ADMITTED",
            "reason": ["HOST_CAP_PLUS_RESERVE_UNAVAILABLE"],
            "memory": m,
            "canonical_memory": m,
            "canonical_policy_sha256": "a",
        }
        admit(w, p, "a", "E18_DIAGNOSTIC_ONLY")
        with self.assertRaises(ValueError):
            admit(w, p, "a", "E20_R0")
        with self.assertRaises(ValueError):
            admit(dict(w, reason=["CONCURRENT_JOB"]), p, "a", "E18_DIAGNOSTIC_ONLY")
        with self.assertRaises(ValueError):
            admit(w, p, "other", "E18_DIAGNOSTIC_ONLY")

    def test_numeric_coverage_must_be_complete(self):
        good = load(BASE.parent / "c270-r0-analysis.json")
        check_gate(good)
        bad = copy.deepcopy(good)
        bad["prospective_witness"]["components"] -= 1
        with self.assertRaises(ValueError):
            check_gate(bad)
        with self.assertRaises(ValueError):
            check_gate(dict(good, full_logits=4))

    def test_recorded_monitor_denies_changed_scope_or_model(self):
        protocol = load(BASE)
        caps = {"memory_high": CAPS["E20_R0"], "memory_max": CAPS["E20_R0"], "swap_max": 0}
        current = file_identity(Path(__file__))
        protocol.update(model_stat=current, parallel_runtime={"libraries_sha256": {"gomp": "d"}})
        sealed = {
            "backend_commit": "backend",
            "ids_sha256": "ids",
            "capture_sha256": "x",
            "numerical_dso_sha256": {"libllama": "h"},
        }
        m = {
            "returncode": 0,
            "stop_reason": None,
            "limits": {"require_telemetry": True},
            "backend_sha": "backend",
            "workload_sha256": "ids",
            "binary_sha256": "x",
            "explicit_env": {"TESY_CPU_WAVE_SKIP_PARKED": "1"},
            "resource_authority": protocol["resources"],
            "artifact_identity": {"stat_at_launch": current, "stat_at_end": current},
            "parallel_runtime": {"libraries_sha256": {"gomp": "d"}},
            "mapped_libraries_match_ldd": True,
            "mapped_backend_libraries_sha256": {"/fixture/libllama": "h"},
            "cgroup_start": caps,
            "cgroup_end": caps,
            "maxima": {"direct_model_fds": 2, "swap_bytes": 0},
        }
        validate_resource_protocol(protocol)
        check_monitor(m, protocol, sealed, "E20_R0")
        with self.assertRaises(ValueError):
            check_monitor(m, protocol, sealed, "E18_DIAGNOSTIC_ONLY")
        with self.assertRaises(ValueError):
            check_monitor(
                dict(m, artifact_identity={"stat_at_launch": current, "stat_at_end": {}}),
                protocol,
                sealed,
                "E20_R0",
            )
