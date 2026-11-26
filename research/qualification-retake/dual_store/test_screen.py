import copy
import json
import unittest
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import screen


def group(n):
    return {
        "layer": 2,
        "experts": [
            {"expert": 10 + j, "slot": j, "generation": 2, "ranges": [[0, 4, 0, 16]] * 3}
            for j in range(n)
        ],
    }


def stats(g, values):
    totals = [sum(values[i : i + 3]) for i in range(0, len(values), 3)]
    return {
        "layer": g["layer"],
        "elapsed_ns": sum(values) + 8,
        "pread_union_ns": max(totals),
        "pread_sum_ns": sum(values),
        "pread_duration_ns": values,
    }


class TestReplay(unittest.TestCase):
    def test_serial_component_choice_binding_and_tie(self):
        result = screen.group_oracle(group(1), [2, 10, 4], [3, 4, 4])
        self.assertEqual((result["nvme_ns"], result["mixed_ns"], result["gain_ns"]), (11, 10, 1))
        j = result["jobs"][0]
        self.assertEqual(j["origin"], ["usb", "nvme", "nvme"])
        self.assertEqual(j["usb_components_whose_reversion_delays_barrier"], ["gate"])
        self.assertEqual(
            result["bytes_by_origin"]["nvme"], {"logical": 8, "requested": 32, "calls": 2}
        )

    def test_off_critical_read(self):
        result = screen.group_oracle(group(2), [1, 1, 1, 5, 5, 5], [2, 2, 2, 5, 5, 5])
        self.assertEqual(result["bytes_by_origin"]["usb"]["calls"], 3)
        self.assertEqual(result["gain_ns"], 0)
        self.assertEqual(result["jobs"][0]["usb_components_whose_reversion_delays_barrier"], [])

    def test_parallel_joint_gain_and_last_switch(self):
        result = screen.group_oracle(group(2), [1, 1, 1, 4, 3, 3], [4, 4, 4, 4, 4, 4])
        self.assertEqual(result["nvme_last_experts"], [10, 11])
        self.assertEqual(result["mixed_last_experts"], [11])
        self.assertEqual(result["gain_ns"], 2)
        self.assertEqual(
            result["jobs"][1]["usb_components_whose_reversion_delays_barrier"], ["down", "up"]
        )

    def test_exact_enumeration_through_four_workers(self):
        for jobs in range(1, 5):
            u = [(i * 7 + 3) % 11 + 2 for i in range(3 * jobs)]
            n = [(i * 5 + 1) % 13 + 1 for i in range(3 * jobs)]
            optimum = None
            for mask in product([0, 1], repeat=len(n)):
                ds = [(u[i], n[i])[origin] for i, origin in enumerate(mask)]
                t = max(sum(ds[j : j + 3]) for j in range(0, len(n), 3))
                optimum = t if optimum is None else min(t, optimum)
            self.assertEqual(screen.group_oracle(group(jobs), u, n)["mixed_ns"], optimum)

    def test_integer_gate_and_conservation(self):
        g = group(1)
        plan = {"groups": [g], "logical_bytes": 12, "aligned_bytes": 48}
        for fast, expected in ((8, True), (9, False), (10, False)):
            result = screen.pair(
                plan, {"groups": [stats(g, [fast, 15, 15])]}, {"groups": [stats(g, [10, 15, 15])]}
            )
            self.assertEqual(result["reaches_five_percent"], expected)
            self.assertEqual(result["breakdown"]["single"]["groups"], 1)
        for passes, status in [
            ([False, True], "INCONCLUSIVE"),
            ([True, True], "GO_SMALL_MIXED_IO_FIXTURE_ONLY"),
            ([False, False], "NO_GO_ORIGIN_SELECTION_FIXED_COMPONENT_SERVICE"),
        ]:
            self.assertEqual(screen.decision(passes), status)

    def test_reject_invalid_duration_identity_and_clocks(self):
        g = group(2)
        plan = {"groups": [g], "logical_bytes": 24, "aligned_bytes": 96}
        measured = stats(g, [2, 4, 8, 2, 4, 8])
        ref = ["f" * 64] * 6
        arm = {
            "status": "PASS",
            "transport": "usb",
            "payload_sha256": ref,
            "service_ns": 36,
            "arm_wall_ns": 55,
            "logical_bytes": 24,
            "requested_bytes": 96,
            "groups": [measured],
        }
        screen.validate_arm(plan, arm, "usb", ref)
        for k, v in (
            ("layer", 3),
            ("pread_duration_ns", [1]),
            ("pread_sum_ns", 14),
            ("pread_union_ns", 13),
            ("elapsed_ns", 13),
        ):
            clone = copy.deepcopy(arm)
            clone["groups"][0][k] = v
            with self.subTest(k=k), self.assertRaises(ValueError):
                screen.validate_arm(plan, clone, "usb", ref)
        for k, v in (
            ("transport", "nvme"),
            ("payload_sha256", ref[::-1][:-1]),
            ("requested_bytes", 95),
            ("arm_wall_ns", 1),
        ):
            with self.subTest(k=k), self.assertRaises(ValueError):
                screen.validate_arm(plan, dict(arm, **{k: v}), "usb", ref)

    def test_manifest_content_and_size(self):
        with TemporaryDirectory() as d:
            file = Path(d) / "arm.json"
            first = b"123"
            file.write_bytes(first)
            self.assertEqual(screen.authenticated(file, screen.digest(first), 3), first)
            for data in (b"12", b"124"):
                file.write_bytes(data)
                with self.assertRaises(ValueError):
                    screen.authenticated(file, screen.digest(first), 3)

    def test_frozen_topology_and_range_failures(self):
        # Synthetic geometry and ranges with the C135 cardinalities.
        plan = {
            "call": 3,
            "position": 2197,
            "component_order": list(screen.COMPONENTS),
            "groups": [],
            "loads": 20,
            "logical_bytes": 0,
            "aligned_bytes": 0,
        }
        for layer, n in enumerate([4, 2] + [1] * 14):
            g = group(n)
            g.update(layer=layer, wait_end_us=layer + 1000)
            for job in g["experts"]:
                job["ranges"] = [[0, 4406400, 0, 4407296]] * 3
                plan["logical_bytes"] += 4406400 * 3
                plan["aligned_bytes"] += 4407296 * 3
            plan["groups"].append(g)
        screen.validate_plan(plan)
        for mutate in (
            lambda p: p["groups"][0]["experts"][0].update(generation=0),
            lambda p: p["groups"][1].update(wait_end_us=1000),
            lambda p: p["groups"][0]["experts"][0]["ranges"][1].__setitem__(0, 4096),
            lambda p: p["component_order"].reverse(),
        ):
            clone = json.loads(json.dumps(plan))
            mutate(clone)
            with self.assertRaises(ValueError):
                screen.validate_plan(clone)


if __name__ == "__main__":
    unittest.main()
