"""Offline checks for the E20 startup admission and runtime budgets."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prefault_ready_entry", HERE / "start.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class ReadyTests(unittest.TestCase):
    def test_independent_and_experimental_profiles(self):
        independent = entry.full.Profile()
        experimental = entry.Profile()
        self.assertFalse(hasattr(independent, "runtime_overlay"))
        self.assertEqual(independent.paging_cap_bytes, 10 << 30)
        self.assertEqual(experimental.paging_cap_bytes, 20 << 30)
        self.assertIsNone(experimental.probe)
        self.assertFalse(experimental.probe_started)

    def test_overlay_directory_rejects_shadowing_and_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            candidate.mkdir()
            image = candidate / entry.IMAGE
            image.write_bytes(b"test")
            for name in ("libllama.so", entry.SONAME):
                (candidate / name).symlink_to(entry.IMAGE)
            self.assertEqual(entry.candidate_image(root), image)
            extra = candidate / "glibc-hwcaps"
            extra.mkdir()
            with self.assertRaisesRegex(ValueError, "other_provider"):
                entry.candidate_image(root)
            extra.rmdir()
            (candidate / entry.SONAME).unlink()
            (candidate / entry.SONAME).symlink_to(Path(__file__))
            with self.assertRaisesRegex(ValueError, "other_provider"):
                entry.candidate_image(root)

    def test_window_must_follow_attribution(self):
        rows = [{"utc": "2026-11-25T04:20:00+00:00"}, {"utc": "2026-11-25T04:21:00+00:00"}]
        window = {"samples": 2, "span_s": 60}
        now = entry.datetime(2026, 11, 25, 4, 22, tzinfo=entry.UTC)
        ends = [("04:19:59", True), ("04:20:00", False), ("04:20:01", False)]
        for stamp, valid in ends:
            proof = {"finished_utc": f"2026-11-25T{stamp}+00:00"}
            if valid:
                self.assertEqual(entry.fresh_c55(rows, proof, window, now=now)[0], rows[0]["utc"])
            else:
                with self.assertRaisesRegex(ValueError, "must_follow"):
                    entry.fresh_c55(rows, proof, window, now=now)

    def test_loader_must_resolve_every_pinned_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock = Path(tmp)
            image = stock / "candidate" / entry.IMAGE
            image.parent.mkdir()
            image.touch()
            sibling = stock / "libggml.so.0"
            sibling.touch()
            exe = stock / "server"
            dsos = [entry.SONAME, sibling.name]
            lines = f"{entry.SONAME} => {image} (0x1)\n{sibling.name} => {sibling} (0x2)\n"
            with patch.object(entry.subprocess, "check_output", return_value=lines):
                self.assertEqual(len(entry.check_loader(exe, image, dsos, {})), 64)
            for bad in (lines.splitlines()[0], lines.replace(str(image), str(sibling))):
                with patch.object(entry.subprocess, "check_output", return_value=bad):
                    with self.assertRaisesRegex(ValueError, "did_not_select"):
                        entry.check_loader(exe, image, dsos, {})

    def test_ready_needs_candidate_present_and_original_absent(self):
        guard = entry.Experiment(None, None, None, None, None, None, {})
        guard.original, guard.candidate = (0, 1, 2), (0, 1, 3)
        for live, admissible in [
            (set(), False),
            ({guard.original}, False),
            ({guard.original, guard.candidate}, False),
            ({guard.candidate}, True),
        ]:
            with patch.object(guard, "verify_candidate_stat"):
                self.assertEqual(all(guard.mapping(live).values()), admissible)

    def test_disk_limit_drives_stop_and_final_check_independently_of_cgroup_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev = root / "nvme0n1"
            dev.mkdir()
            (dev / "dev").write_text("259:0")
            path, identity = entry.nvme_counter("/dev/nvme0n1p3[/root]", root)
            record = {"io_stat_delta_by_device": {identity: {"rbytes": 0}}}
            guard = entry.Experiment(root, None, None, path, identity, root, record)
            guard.start_bytes = 512
            for sectors, fails in [(2, False), ((entry.READ_LIMIT // 512) + 1, True), (0, True)]:
                path.write_text(f"0 0 {sectors} 0 0 0 0 0 0 0 0")
                with patch.object(guard, "require_window"):
                    if fails:
                        with self.assertRaisesRegex(ValueError, "1TiB"):
                            guard.watch()
                        with self.assertRaisesRegex(ValueError, "1TiB"):
                            guard.finish(record)
                    else:
                        self.assertEqual(guard.watch(), 512)
                        guard.finish(record)
                        self.assertEqual(record["model_device_cgroup_rbytes"], 0)
                        self.assertEqual(record["model_device_physical_read_delta_bytes"], 512)
            with self.assertRaisesRegex(ValueError, "not_an_nvme_namespace"):
                entry.nvme_counter("/dev/sda", root)

    def test_pinned_public_evidence_and_substitutions(self):
        # The independent attribution unit publishes this file together with this gate.
        receipt = entry.RESIDENT / "attribution-r2/receipt.json"
        digest = (HERE / "attribution.sha256").read_text().strip()
        overlay = entry.sealed_json(
            HERE.parent / "stock_prefault_build/build-r1/receipt.json", entry.OVERLAY
        )
        if not receipt.exists():
            self.skipTest("attribution-r2 public receipt has not been placed in the checkout")
        proof = entry.sealed_json(receipt, digest)
        entry.check_attribution(proof, overlay)
        with self.assertRaisesRegex(ValueError, "receipt_sha256"):
            entry.sealed_json(receipt, "0" * 64)
        for field, value in [
            ("memory_max_bytes", 1),
            ("clean", False),
            ("status", "FAIL_PRESERVED"),
        ]:
            with self.assertRaisesRegex(ValueError, "attribution"):
                entry.check_attribution({**proof, field: value}, overlay)
        for arm, field, wrong in [
            ("ON", "maps", [[50816, 0, 1, 32769]]),
            ("OFF", "logits_compared", 1),
            ("stock", "execution_by_prompt", []),
            ("invalid", "exit", 0),
        ]:
            bad = json.loads(json.dumps(proof))
            bad["arms"][arm][field] = wrong
            with self.assertRaisesRegex(ValueError, "attribution"):
                entry.check_attribution(bad, overlay)


if __name__ == "__main__":
    unittest.main()
