import struct
import unittest
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

p = run_path(Path(__file__).with_name("profile.py"))
ACTUAL = p["ACTUAL"]


def result(mode):
    victims = list(range(5)) if mode == "R0" else list(range(35, 40))
    data = dict(
        status="PASS_C291_CPU0_DETECTED_MUTATION"
        if mode == "MUTANT"
        else "PASS_C291_CPU0_POLICY_TILE",
        arm=mode,
        backing_enabled=mode != "R0",
        bias_nodes_observed=24,
        router_positions=153,
        ffn_positions=32,
        full_ffn_values=92160,
        graph_waves=8,
        active_waves=1,
        mmid_nodes_observed=24,
        compute_backend="CPU",
        workers_before_destructor=4,
        joined_workers=4,
        manager_destructor_returned=True,
        unique_loads=45,
        pread_bytes=594984960,
        logical_weight_bytes=594864000,
        weight_sets=135,
        seed_roles_verified=120,
        backing_roles_verified=15,
        backing_bytes=66096000,
        backing_experts=list(range(35, 40)),
        selected_weight_roles=15,
        selected_bias_roles=15,
        evicted_experts=victims,
        weight_mismatches=[[45, "gate"], [49, "gate"]] if mode == "MUTANT" else [],
        fd_odirect=True,
        fd_stat=dict(dev=1, ino=2, size=3, mtime_ns=4, ctime_ns=5),
        selected_bindings=[[e, s, 2] for e, s in zip(ACTUAL, victims, strict=True)],
        ffn_unequal=int(mode == "MUTANT"),
        providers={"crypto": "/usr/lib64/libcrypto.so.3"},
    )
    return data


class Policy(unittest.TestCase):
    def test_discriminating_policy_and_mutant(self):
        identity = dict(dev=1, inode=2, size_bytes=3, mtime_ns=4, ctime_ns=5)
        for mode, field, value, message in (
            ("R0", "backing_enabled", True, "backing_enabled"),
            ("BACKED", "selected_bindings", result("R0")["selected_bindings"], "bindings"),
            ("MUTANT", "ffn_unequal", 0, "FFN mismatch"),
            ("MUTANT", "weight_mismatches", [[45, "up"], [49, "up"]], "weight_mismatches"),
            ("R0", "fd_stat", {"dev": 2}, "fd_stat"),
        ):
            with self.subTest(mode=mode, field=field):
                data = result(mode) | {field: value}
                with self.assertRaisesRegex(ValueError, message):
                    p["verify_arm"](
                        data, mode, {e: ["a", "b", "c"] for e in ACTUAL}, identity, None, None
                    )

    def test_complete_float_rows_and_counterexample(self):
        with TemporaryDirectory() as root:
            f = Path(root) / "tile.f32"
            gold = bytes(368640)
            f.write_bytes(gold)
            self.assertEqual(p["vector"](f, gold, "BACKED")["values"], 92160)
            with self.assertRaisesRegex(ValueError, "tile control"):
                p["vector"](f, gold, "MUTANT")
            f.write_bytes(struct.pack("<f", 1.0) + gold[4:])
            self.assertEqual(p["vector"](f, gold, "MUTANT")["changed_f32_bit_patterns"], 1)
            with self.assertRaisesRegex(ValueError, "tile control"):
                p["vector"](f, gold, "BACKED")

    def test_original_inputs_and_shared_helpers(self):
        prior, service = p["shared"]()
        self.assertEqual(prior.CAP, p["CAP"])
        self.assertEqual(service.WALL, p["WALL"])
        self.assertEqual(p["MAX_OUT"], 16 * 1024**2)


if __name__ == "__main__":
    unittest.main()
