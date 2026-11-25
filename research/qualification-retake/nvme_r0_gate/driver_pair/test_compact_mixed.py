"""Replay literal LD_DEBUG paths after the original private aliases have disappeared."""

import unittest
from pathlib import PurePosixPath
from unittest.mock import patch

from compact_mixed import archived_initializers


class ArchivedPaths(unittest.TestCase):
    def test_no_current_files_are_needed(self):
        aliases = "/historical/campaign-does-not-exist/driver"
        libs = "/historical/nonexistent-signed-deployment/files/lib/"
        driver = libs + "libcuda.so.620.70.06"
        nvvm = libs + "libnvidia-nvvm70.so.4"
        startup = {"libcuda.so.1": [aliases + "/libcuda.so.1", driver]}
        signed = {
            "libcuda.so.1": PurePosixPath(driver),
            "libnvidia-nvvm70.so.4": PurePosixPath(nvvm),
        }
        files = {driver: {"sha256": "a" * 64}, nvvm: {"sha256": "b" * 64}}
        post = {PurePosixPath(k).name: v["sha256"] for k, v in files.items()}
        log = "\n".join("  21: calling init: " + aliases + "/" + k for k in signed)

        def read(text=log, prior=startup, end=post):
            return archived_initializers(text, 21, prior, signed, files, end)

        with (
            patch("os.stat", side_effect=AssertionError("live stat")),
            patch("os.lstat", side_effect=AssertionError("live lstat")),
            patch("os.readlink", side_effect=AssertionError("live symlink")),
        ):
            self.assertEqual(read(), set(files))
            for change in (
                log.replace(aliases + "/libnvidia", "/lib64/libnvidia"),
                log.replace("21:", "22:"),
                log.replace("/driver/libcuda", "/driver/../driver/libcuda"),
            ):
                with self.assertRaises(ValueError):
                    read(change)
            with self.assertRaises(ValueError):
                read(end={})
            with self.assertRaises(ValueError):
                read(prior={"libcuda.so.1": [aliases + "/libcuda.so.1", nvvm]})


if __name__ == "__main__":
    unittest.main()
