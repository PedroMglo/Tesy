"""Exercise c2_server_run.run through the actual Popen boundary, without a model."""

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c118_start_inventory import collect
from run_bounded import sha256


REPO = Path(__file__).resolve().parents[1]
OLD = REPO / "results/c117-operational-nominal-server-20260929T1058Z"
RUN_IDS = ("c120-p1-control", "c120-p1-candidate",
           "c120-p2-candidate", "c120-p2-control")


class SpawnReached(Exception):
    pass


class TestPrelaunchEntrypoint(unittest.TestCase):
    def fixture(self, root, run_id, *, bad=None):
        (root / "raw").mkdir()
        policy = strict_json((OLD / "resource-policy.json").read_text())
        (root / "resource-policy.json").write_text(json.dumps(policy))
        old = strict_json((OLD / "protocols/c117-p1-control.json").read_text())
        old["start_inventory"] = {"schema": "c120-start-inventory-v1",
            "duration_s": 60, "max_age_s": 3,
            "policy_sha256": sha256(root / "resource-policy.json")}
        protocol_path = root / "protocol.json"
        protocol_path.write_text(json.dumps(old))
        config = {"output_root": str(root / "raw"), "server_command": ["/bin/true"],
                  "explicit_env": {}, "request_policy": {"max_tokens": 1}}
        model = root / "dummy-model"
        model.write_bytes(b"x")
        clock = [100000.0]
        utc_base = datetime.now(timezone.utc) - timedelta(seconds=60)
        def observation():
            return {"thermal": {"cpu_tctl_c": 50,
                    "nvme_composite_by_sensor": {row["sensor"]: 40 for row in policy["nvme"]}},
                    "gpu": {"uuid": policy["gpu"]["uuid"],
                            "bdf": policy["gpu"]["bdf"], "temperature_c": 45,
                            "used_mib": 12},
                    "power": {"source": "AC", "profile": "performance"},
                    "mem_available_bytes": 26 * 2**30}
        def sleep(seconds):
            clock[0] += seconds
        receipt = collect(root, run_id, policy=policy, cap_bytes=18 * 2**30,
                          expected_power={"source": "AC", "profile": "performance"},
                          sample=observation, monotonic=lambda: clock[0],
                          sleep=sleep, duration_s=60,
                          utc_now=lambda: utc_base + timedelta(seconds=clock[0]-100000))
        receipt_path = root / "raw" / f"{run_id}.start-inventory.receipt.json"
        if bad == "missing":
            (root / "raw" / f"{run_id}.start-inventory.jsonl").unlink()
        elif bad == "wrong_arm":
            receipt["run_id"] = "other-arm"
        elif bad == "bad_cap":
            receipt["cap_bytes"] += 1
        elif bad == "old":
            raw_path = root / "raw" / f"{run_id}.start-inventory.jsonl"
            rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
            for row in rows:
                row["utc"] = (datetime.fromisoformat(row["utc"]) -
                              timedelta(hours=1)).isoformat()
            raw_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            receipt["last_utc"] = rows[-1]["utc"]
            receipt["sha256"] = sha256(raw_path)
        receipt_path.write_text(json.dumps(receipt))
        return old, config, model, protocol_path, observation

    def exercise(self, run_id, bad=None):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            protocol, config, model, protocol_path, observation = self.fixture(root, run_id, bad=bad)
            sample = observation()
            cgroup = {"memory_max": 18 * 2**30, "swap_max": 0, "path": "/test"}
            args = SimpleNamespace(run_id=run_id, protocol=protocol_path,
                                   suite="c120nominal", model="target120b")
            spawn = MagicMock(side_effect=SpawnReached)
            with patch.object(server, "cgroup_state", return_value=cgroup), \
                 patch.object(server, "mem_available", return_value=26 * 2**30), \
                 patch.object(server, "gpu_state", return_value=sample["gpu"]), \
                 patch.object(server, "thermal_state", return_value=sample["thermal"]), \
                 patch("host_resource_policy.live_power", return_value={
                       "source": "AC", "profile": "performance",
                       "online_sources": policy_power_sources(protocol)}), \
                 patch("host_resource_policy.host_pressure", return_value=0), \
                 patch.object(server.socket, "socket") as socket_mock, \
                 patch.object(server.subprocess, "Popen", spawn):
                socket_mock.return_value.__enter__.return_value.bind.return_value = None
                if bad is None:
                    with self.assertRaises(SpawnReached):
                        server.run(args, protocol, config, [], model)
                    self.assertEqual(spawn.call_count, 1)
                else:
                    with self.assertRaises((GateError, FileNotFoundError)):
                        server.run(args, protocol, config, [], model)
                    self.assertEqual(spawn.call_count, 0)

    def test_four_arm_spawns_and_negative_gates(self):
        for run_id in RUN_IDS:
            with self.subTest(run_id=run_id, case="good"):
                self.exercise(run_id)
            for bad in ("missing", "wrong_arm", "bad_cap", "old"):
                with self.subTest(run_id=run_id, case=bad):
                    self.exercise(run_id, bad=bad)


def policy_power_sources(protocol):
    return protocol["resources"]["power"]["online_sources"]


if __name__ == "__main__":
    unittest.main()
