import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import probe
import run


class ProbeTests(unittest.TestCase):
    def test_separate_partition_missing_and_duplicate(self):
        text = "259:3 rbytes=8192 rios=2\n259:0 rios=1 rbytes=4096\n"
        self.assertEqual(probe.counters(text, "259:0"), (4096, 1))
        self.assertEqual(probe.counters(text, "8:0"), (-1, -1))
        for bad in [text + text, "259:0 rbytes=1 rbytes=2 rios=1", "259:0 rbytes=-1 rios=1"]:
            with self.assertRaises(ValueError):
                probe.counters(bad, "259:0")

    def test_reader_uses_bracket_and_sector_field(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "io.stat").write_text("259:0 rbytes=512 rios=1\n")
            disk = base / "block.stat"
            disk.write_text("13 19 37 54 31 29 23 17 11 7 5")
            fd = os.open(base, os.O_DIRECTORY)
            try:
                with patch.object(probe.time, "monotonic_ns", side_effect=[123, 135]):
                    self.assertEqual(probe.sample(fd, disk, "259:0"), (123, 135, 512, 1, 37, 11))
            finally:
                os.close(fd)

    def test_different_observer_group_and_sealed_input(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            pid = probe.identity(os.getpid())
            (base / "launch.json").write_text(probe.json.dumps({"process_identity": pid}))
            obs = {}
            probe.physical_observer(
                base / "launch.json",
                Path(pid["cgroup_path"]).name.removesuffix(".service"),
                {},
                base / "invalid.tsv",
                threading.Event(),
                obs,
            )
            self.assertEqual(obs["status"], "OBSERVATION_ERROR")
            self.assertFalse((base / "invalid.tsv").exists())
            with self.assertRaisesRegex(ValueError, "changed"):
                run.pinned(base / "launch.json", "0" * 64)


if __name__ == "__main__":
    unittest.main()
