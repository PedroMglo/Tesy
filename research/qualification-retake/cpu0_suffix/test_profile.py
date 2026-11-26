import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "tesy_cpu0_suffix_profile", Path(__file__).with_name("profile.py")
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def sample(mode):
    return dict(
        mode=mode,
        graph_start_ns=101,
        graph_end_ns=201,
        graph_ns=100,
        wave_return_ns=130 if mode == "ON" else None,
        suffix_ns=71 if mode == "ON" else None,
        wave_markers=int(mode == "ON"),
    )


class NativeBoundaries(unittest.TestCase):
    def test_off_and_on_are_distinct(self):
        self.assertEqual(p.clocks(sample("ON"), "ON")["suffix_ns"], 71)
        self.assertIsNone(p.clocks(sample("OFF"), "OFF")["return_ns"])
        self.assertEqual(p.SCHEDULE, ("OFF", "ON", "ON", "OFF", "ON", "OFF", "OFF", "ON"))

    def test_reject_fake_suffix_or_clock(self):
        for key, value in (
            ("graph_ns", 90),
            ("wave_return_ns", 202),
            ("wave_return_ns", 101),
            ("wave_markers", True),
            ("suffix_ns", 70),
            ("wave_markers", 2),
            ("mode", "OFF"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                p.clocks(sample("ON") | {key: value}, "ON")
        for val in (0, False, 4):
            with self.assertRaises(ValueError):
                p.clocks(sample("OFF") | {"suffix_ns": val}, "OFF")

    def test_graph_bytes_and_witness_rejections(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            native = root / "native"
            native.mkdir()
            tile = native / "tile.f32"
            gold = bytes(92160 * 4)
            tile.write_bytes(gold)
            providers = {}
            digests = {}

            def sha(f):
                return hashlib.sha256(f.read_bytes()).hexdigest()

            for lib in ("cpu", "base"):
                path = root / (lib + ".so")
                path.write_bytes(lib.encode())
                providers[lib] = str(path)
                digests[path.name] = sha(path)
            prior = SimpleNamespace(
                LIB_CODES={"cpu": "cpu.so", "base": "base.so"}, LIBS=digests, sha=sha
            )
            args = SimpleNamespace(libs=root)
            row = sample("ON") | dict(
                status="PASS_C291_CPU0_SUFFIX",
                arm="DENSE",
                compute_backend="CPU",
                router_positions=153,
                ffn_positions=32,
                full_ffn_values=92160,
                graph_waves=8,
                roles=["gate", "down", "up"],
                dio_offset_alignment=4096,
                cb_eval_registered=False,
                graph_mmid_nodes=24,
                wave_calls=8,
                active_waves=1,
                unique_loads=5,
                logical_weight_bytes=66096000,
                expected_pread_bytes=66109440,
                expected_weight_sets=15,
                workers_before_destructor=4,
                joined_workers=4,
                manager_destructor_returned=True,
                graph_nodes=99,
                backend_splits=1,
                graph_fingerprint="abc0123456789def",
                providers=providers,
            )
            with mock.patch.object(p, "GOLD", sha(tile)):
                self.assertEqual(
                    p.verify(args, prior, row, "ON", native, gold)["tile_sha256"], sha(tile)
                )
                for k, v in (
                    ("cb_eval_registered", True),
                    ("graph_mmid_nodes", 23),
                    ("unique_loads", 4),
                    ("joined_workers", 3),
                    ("expected_pread_bytes", 66096000),
                ):
                    with self.subTest(k=k), self.assertRaises(ValueError):
                        p.verify(args, prior, row | {k: v}, "ON", native, gold)
                tile.write_bytes(b"\0" * 4 + b"\1" * (len(gold) - 4))
                with self.assertRaisesRegex(ValueError, "bitwise"):
                    p.verify(args, prior, row, "ON", native, gold)


if __name__ == "__main__":
    unittest.main()
