import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "parked_mmid_profile", Path(__file__).with_name("profile.py")
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.cpu0 = p.cpu0_module()
        self.prior = self.cpu0.module(
            p.HERE.parents[1] / "packed_real_layer/profile.py", "parked_test_prior", self.cpu0.LAYER
        )
        cpu, base = self.prior.LIB_CODES.values()
        self.libs = self.path / "libs"
        self.libs.mkdir()
        cand = self.path / "candidate"
        cand.mkdir()
        for path, data in [
            (self.libs / cpu, b"original"),
            (cand / cpu, b"patched"),
            (self.libs / base, b"base"),
        ]:
            path.write_bytes(data)
        self.ref = dict(
            provider_sha256={n: sha(self.libs / n) for n in (cpu, base)},
            graph_nodes=110,
            graph_fingerprint="e569253a2f984a84",
            backend_splits=1,
        )
        self.build = dict(
            original_cpu_sha256=sha(self.libs / cpu),
            candidate_cpu_sha256=sha(cand / cpu),
            base_sha256=sha(self.libs / base),
        )
        self.args = SimpleNamespace(libs=self.libs, build_dir=self.path)

    def test_same_patched_dso_and_disabled_observer(self):
        modes = [p.settings(self.args, self.prior, self.ref, self.build, m) for m in p.QUALIFY]
        (orig, original), (off, patched), (on, enabled) = modes
        self.assertEqual(patched, enabled)
        self.assertNotEqual(original["cpu"], patched["cpu"])
        self.assertNotIn(p.MODE_ENV, orig)
        self.assertEqual(on, off | {p.MODE_ENV: "1"})
        self.assertEqual(off[p.MODE_ENV], "0")
        self.assertTrue(all(env["TESY_CPU_SUFFIX"] == "OFF" for env, _ in modes))
        with self.assertRaisesRegex(ValueError, "identity"):
            p.settings(
                self.args,
                self.prior,
                self.ref,
                self.build | {"base_sha256": self.build["original_cpu_sha256"]},
                "ON",
            )

    def test_complete_prior_qualification_excluded_from_pairs(self):
        rows = [
            dict(
                mode=m,
                graph_ns=i + 10,
                run_index=i,
                phase="qualification" if i < 3 else "timing",
                status="PASS_PARKED_MMID_TILE_ARM",
                returncode=0,
                child_started=True,
                observer="OFF",
            )
            for i, m in enumerate(p.QUALIFY + p.SCHEDULE)
        ]
        self.assertEqual([r["graph_ns"] for r in p.timing_input(rows)], list(range(13, 21)))
        for i, delta in (
            (0, {"mode": "OFF"}),
            (2, {"status": "FAIL_PRESERVED"}),
            (6, {"observer": "ON"}),
            (10, {"phase": "qualification"}),
        ):
            with self.subTest(i=i), self.assertRaises(ValueError):
                p.timing_input(rows[:i] + [rows[i] | delta] + rows[i + 1 :])

    def test_native_rejects_swap_graph_marks_and_output_mismatch(self):
        _, providers = p.settings(self.args, self.prior, self.ref, self.build, "ON")
        native = self.path / "native"
        native.mkdir()
        tile = native / "tile.f32"
        gold = bytes(368640)
        tile.write_bytes(gold)
        row = dict(
            status="PASS_C291_CPU0_SUFFIX",
            arm="DENSE",
            mode="OFF",
            clock="CLOCK_MONOTONIC",
            compute_backend="CPU",
            roles=["gate", "down", "up"],
            cb_eval_registered=False,
            marked_graph_threads=0,
            graph_mmid_nodes=24,
            router_positions=153,
            ffn_positions=32,
            full_ffn_values=92160,
            graph_waves=8,
            wave_calls=8,
            active_waves=1,
            unique_loads=5,
            logical_weight_bytes=66096000,
            expected_pread_bytes=66109440,
            expected_weight_sets=15,
            workers_before_destructor=4,
            joined_workers=4,
            manager_destructor_returned=True,
            graph_nodes=110,
            graph_fingerprint=self.ref["graph_fingerprint"],
            backend_splits=1,
            graph_start_ns=10,
            graph_end_ns=50,
            graph_ns=40,
            wave_markers=0,
            suffix_ns=None,
            wave_return_ns=None,
            dio_offset_alignment=4096,
            providers={k: str(v[0]) for k, v in providers.items()},
        )

        def verify(r):
            return p.native_row(self.prior, self.cpu0, self.ref, r, providers, native, gold)

        with mock.patch.object(self.cpu0, "GOLD", sha(tile)):
            self.assertEqual(verify(row)["tile_bytes"], 368640)
            for key, bad in (
                (
                    "providers",
                    row["providers"] | {"cpu": str(self.libs / self.prior.LIB_CODES["cpu"])},
                ),
                ("backend_splits", 2),
                ("wave_markers", 1),
                ("clock", "CLOCK_REALTIME"),
                ("cb_eval_registered", True),
                ("joined_workers", 3),
            ):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    verify(row | {key: bad})
            tile.write_bytes(b"1" + gold[1:])
            with self.assertRaisesRegex(ValueError, "bitwise"):
                verify(row)

    def test_conditional_conversion_and_three_independent_raws(self):
        for m in ("r0", "off", "on"):
            (self.path / f"fixture-{m}.bin").write_bytes(bytes(98304))
        exe = self.path / "test-kernel-graph"
        exe.write_bytes(b"test")
        digest = sha(self.path / "fixture-r0.bin")
        fixture = dict(
            numerical_fixture_sha256=digest,
            fixture_executable_sha256=sha(exe),
            synthetic_rows={m: dict(bytes=98304, sha256=digest) for m in ("r0", "off", "on")},
            fixture_stdout={
                m: (
                    f"PASS_PARKED_MMID_GRAPH cases=192 skipped={24 if m == 'on' else 0}"
                    " rows_bytes=98304"
                )
                for m in ("r0", "off", "on")
            },
        )
        p.synthetic_gate(fixture, self.path, self.prior)
        with self.assertRaisesRegex(ValueError, "coverage"):
            p.synthetic_gate(
                fixture
                | {
                    "fixture_stdout": fixture["fixture_stdout"]
                    | {"on": fixture["fixture_stdout"]["off"]}
                },
                self.path,
                self.prior,
            )
        (self.path / "fixture-on.bin").write_bytes(bytes(98303) + b"1")
        with self.assertRaises(ValueError):
            p.synthetic_gate(fixture, self.path, self.prior)


if __name__ == "__main__":
    unittest.main()
