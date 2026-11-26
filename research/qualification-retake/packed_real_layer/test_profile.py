"""Synthetic controls for CPU0 supervisor; no device, GGUF, model client or cgroup."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "cpu0_profile", Path(__file__).with_name("profile.py")
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class Gates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.args = SimpleNamespace(libs=self.root)
        self.out = self.root / "arm"
        self.out.mkdir()
        self.gold = b"xyzw" * 92160
        (self.out / "tile.f32").write_bytes(self.gold)
        self.providers = {}
        for k, name in mod.LIB_CODES.items():
            p = self.root / name
            p.write_bytes(bytes([len(k)]))
            self.providers[k] = str(p)
        self.patch = patch.dict(
            mod.LIBS, {p.name: mod.sha(p) for p in self.root.iterdir() if p.is_file()}
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def row(self, arm="DIRECT"):
        return dict(
            status=mod.TILE_STATUS,
            arm=arm,
            router_positions=153,
            ffn_positions=32,
            full_ffn_values=92160,
            graph_waves=8,
            active_waves=1,
            mmid_nodes_observed=24,
            compute_backend="CPU",
            weight_sets=0 if arm == "DIRECT" else 15,
            unique_loads=5,
            roles=["gate", "down", "up"],
            logical_weight_bytes=66096000,
            workers_before_destructor=4,
            joined_workers=4,
            manager_destructor_returned=True,
            providers=self.providers,
            dio_offset_alignment=512,
            pread_bytes=5 * 13221888 if arm != "DENSE" else 5 * 13219328,
        )

    def check(self, row):
        return mod.verify_arm(self.args, row, row["arm"], self.out, self.gold)

    def test_same_gold_and_transport_per_arm(self):
        for arm in mod.ARMS:
            self.assertEqual(self.check(self.row(arm)), mod.sha(self.out / "tile.f32"))

    def test_short_witness_and_accidental_equality(self):
        for key, value in (
            ("joined_workers", 3),
            ("manager_destructor_returned", 1),
            ("roles", ["gate", "up", "down"]),
            ("weight_sets", 15),
            ("mmid_nodes_observed", 21),
            ("compute_backend", "CUDA0"),
            ("pread_bytes", 66096000),
            ("dio_offset_alignment", 0),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.row(), **{key: value}))

    def test_copied_dso_at_wrong_identity(self):
        wrong = self.root / "different"
        orig = Path(self.providers["cpu"])
        wrong.write_bytes(orig.read_bytes())
        with self.assertRaises(ValueError):
            self.check(dict(self.row(), providers={**self.providers, "cpu": str(wrong)}))

    def test_last_float_and_partial_publication(self):
        result = self.out / "tile.f32"
        for content in (self.gold[:-1] + b"0", self.gold[:-4]):
            result.write_bytes(content)
            with self.assertRaises(ValueError):
                self.check(self.row())

    def test_single_controller_and_mode_env(self):
        self.assertNotIn("TESY_PACKED_CPU_SLOTS", mod.child_env(self.args, "DENSE"))
        for arm in ["DIRECT", "STAGED"]:
            self.assertEqual(mod.child_env(self.args, arm)["TESY_PACKED_CPU_SLOTS"], arm.lower())
        with self.assertRaises(FileExistsError):
            mod.put(self.out / "tile.f32", {"status": "replaced"})
        self.assertEqual((self.out / "tile.f32").read_bytes(), self.gold)


if __name__ == "__main__":
    unittest.main()
