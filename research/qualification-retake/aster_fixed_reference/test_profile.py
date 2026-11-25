"""Fixed-history controller tests with fabricated kernel observables only."""

import importlib.util
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fixed_aster_controller", HERE / "profile.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class Probe:
    timeout_s = 3000
    run_id = "stock-aster-fixed-natural-reference"
    pass_status = "PASS_FIXED_ASTER_NATURAL_ENVELOPE"
    ram_profile = "E10"
    protocol_path = HERE / "protocol.md"


class Tests(unittest.TestCase):
    def test_provider_absence_and_deleted_shadow(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            original = directory / "libllama.so.0.9.0"
            original.touch()
            (directory / "libllama.so.0").symlink_to(original)
            maps = f"100-200 r-xp 0 00:01 7 {original}\n"
            env = f"LD_LIBRARY_PATH={directory}\0".encode()
            p.stock_maps(env, maps, directory)
            for bad in ("LD_PRELOAD", "LD_AUDIT", "TESY_STOCK_LAZY_MMAP", "TESY_F32_PROFILE"):
                with self.assertRaisesRegex(ValueError, "provider"):
                    p.stock_maps(env + f"{bad}=0\0".encode(), maps, directory)
            for name in (
                "/elsewhere/libllama.so.0",
                str(original) + " (deleted)",
                "/x/observer.so",
            ):
                with self.assertRaises(ValueError):
                    p.stock_maps(env, maps + f"300-400 r-xp 0 00:01 9 {name}\n", directory)

    def test_window_bound_to_prospective_E10_with_host_reserve(self):
        t = p.PROTOCOL_UTC + timedelta(seconds=5)
        rows = [{"utc": (t + timedelta(seconds=i)).isoformat()} for i in range(61)]
        memory = dict(
            reserve_bytes=2 * p.core.GIB,
            available_min_bytes=12 * p.core.GIB,
            cap_max_bytes=10 * p.core.GIB,
        )
        win = dict(memory=memory, canonical_memory=memory, samples=61, span_s=60)
        p.check_window(win, {"memory": memory}, rows, t + timedelta(seconds=60))
        for values in (
            [dict(utc=p.PROTOCOL_UTC.isoformat()), *rows[1:]],
            rows[:-1],
        ):
            with self.assertRaisesRegex(ValueError, "new_C55"):
                p.check_window(win, {"memory": memory}, values, p.END)
        with self.assertRaisesRegex(ValueError, "reserve"):
            p.check_window(win, {"memory": dict(memory, reserve_bytes=1)}, rows, p.END)

    def test_five_tib_inclusive_stop_and_child_accounting(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw"
            raw.mkdir()
            (raw.parent / "inventory").write_bytes(bytes(3))
            (raw / "nested").mkdir()
            (raw / "nested/stream").write_bytes(bytes(8))
            stat = Path(d).parent / "unused"
            run = p.Experiment(p.Profile(Probe), stat, "1:0", raw, {})
            run.start_bytes = 512
            with (
                patch.object(run, "require_window"),
                patch.object(p.shared, "bytes_read", return_value=p.READ_LIMIT),
            ):
                record = {"io_stat_delta_by_device": {"1:0": {"rbytes": 1024}}}
                run.finish(record)
                self.assertEqual(
                    record["model_device_physical_read_delta_bytes"], p.READ_LIMIT - 512
                )
                self.assertEqual(record["model_device_cgroup_rbytes"], 1024)
                self.assertEqual(record["raw_size_bytes"], 11)
                with self.assertRaisesRegex(ValueError, "5TiB"):
                    run.enforce(p.READ_LIMIT, 0)
                with self.assertRaisesRegex(ValueError, "64MiB"):
                    run.enforce(0, p.RAW_LIMIT + 1)
                with self.assertRaisesRegex(ValueError, "accounting"):
                    run.finish({"io_stat_delta_by_device": {}})

    def test_no_600s_stop_and_full_window_before_C118(self):
        prof = p.Profile(Probe)
        self.assertEqual(prof.paging_cap_bytes, 10 * p.core.GIB)
        run = p.Experiment(prof, None, None, Path("/tmp/mock/raw"), {})
        with patch.object(p, "datetime") as utc, patch.object(p.time, "monotonic") as tick:
            utc.now.return_value = p.END - timedelta(seconds=3251)
            tick.return_value = prof.started
            run.require_window(250)
            utc.now.return_value = p.END - timedelta(seconds=3250)
            with self.assertRaisesRegex(ValueError, "cutoff"):
                run.require_window(250)
            tick.return_value = prof.started + 602
            utc.now.return_value = p.END - timedelta(seconds=2600)
            run.require_window(0)
            tick.return_value = prof.started + 3300
            with self.assertRaisesRegex(ValueError, "cutoff"):
                run.require_window(0)

    def test_original_stock_identity_reuses_eight_bindings(self):
        run = p.Experiment(SimpleNamespace(), None, None, Path("/tmp/mock/raw"), {})
        bindings = {p.shared.SONAME: (0, 7, 3), "libggml.so.1": (1, 9, 15)}
        original = bindings.copy()
        run.bind(None, bindings)
        self.assertEqual(bindings, original)
        self.assertTrue(run.mapping({(0, 7, 3)})["original_stock_libllama_present"])
        self.assertFalse(run.mapping({(1, 9, 15)})["original_stock_libllama_present"])


if __name__ == "__main__":
    unittest.main()
