import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live  # noqa: E402

profile = live.linkage.load_module(HERE / "profile.py", "c292_test_profile")


class Capture(unittest.TestCase):
    def test_live_pack_identity_flags_and_fd_uniqueness(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            pack = p / "pack"
            pack.write_bytes(b"fake")
            stat = live.static.derive.runtime_stat(pack.stat())
            (p / "fd").mkdir()
            (p / "fdinfo").mkdir()
            self.assertEqual(live.proc_pack(p, pack, stat), [])
            fd = p / "fd/7"
            fd.symlink_to(pack)
            info = p / "fdinfo/7"

            def flags(n):
                info.write_text(f"pos:\t0\nflags:\t0{n:o}\n")

            flags(os.O_DIRECT)
            self.assertEqual(live.proc_pack(p, pack, stat), [(7, os.O_DIRECT)])
            for n in (os.O_RDONLY, os.O_DIRECT | os.O_RDWR):
                flags(n)
                with self.assertRaises(ValueError):
                    live.proc_pack(p, pack, stat)
            flags(os.O_DIRECT)
            with self.assertRaises(ValueError):
                live.proc_pack(p, pack, stat | {"inode": -1})
            (p / "fd/11").symlink_to(pack)
            (p / "fdinfo/11").write_text(info.read_text())
            with self.assertRaises(ValueError):
                live.proc_pack(p, pack, stat)

    def test_failed_off_cannot_claim_a_pack_and_on_requires_a_witness(self):
        for mode, obs in (("OFF", {(4, os.O_DIRECT)}), ("ON", set())):
            ctl = SimpleNamespace(
                mode=mode, env_checked=True, pack_observations=obs, pack_seen=len(obs)
            )
            with self.assertRaises(ValueError):
                live.CaptureAuthority.fd_evidence(ctl)

    def test_command_preserves_ids_and_changes_only_transport_between_arms(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            original = p / "old-bin"
            model = p / "model"
            original.touch()
            model.touch()
            ctl = SimpleNamespace(
                original_search="OLD",
                native_search="NEW",
                backend=p,
                exe=p / "exe",
                original_exe=original,
                data_paths={"model": model, "manifest": p / "manifest"},
            )
            base = [
                str(live.REPO / "tools/run_bounded.py"),
                "--backend-root",
                str(p),
                "--variant",
                "C269-R0-selected189+32-E20_R0",
                "--resource-protocol",
                str(p / "protocol.json"),
                "--timeout-s",
                "240",
                "--env",
                "TESY_CPU_WAVE_SKIP_PARKED=1",
                "--env",
                "LD_LIBRARY_PATH=OLD",
                "--",
                str(original),
                str(model),
                "ids",
                "capture",
                "--ngl",
                "12",
            ]
            off = profile.command(base, ctl, p, "OFF", p)
            on = profile.command(base, ctl, p, "ON", p)
            self.assertFalse(any("TESY_EXPERT_STORE_MANIFEST" in x for x in off))
            self.assertIn("TESY_EXPERT_STORE_MANIFEST=" + str(p / "manifest"), on)
            self.assertEqual(off[-6:], on[-6:])
            with self.assertRaises(ValueError):
                profile.command([x if x != "240" else "600" for x in base], ctl, p, "ON", p)

    def test_c55_window_bound(self):
        now = datetime.now(UTC)
        policy = {"snapshot": {"utc": now.isoformat()}}
        self.assertEqual(profile.age(policy, now + timedelta(seconds=3599)), 3599)
        with self.assertRaises(ValueError):
            profile.age(policy, now + timedelta(seconds=3600))


if __name__ == "__main__":
    unittest.main()
