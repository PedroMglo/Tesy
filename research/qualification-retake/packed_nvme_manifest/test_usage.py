"""Reproduce high-water retention over exec with only anonymous memory."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import usage  # noqa: E402

SMALL = 32 * 2**20


def demonstrate(use_time, out):
    # Only the sacrificial fork allocates and touches these pages.
    pid = os.fork()
    if pid == 0:
        data = bytearray(48 * 2**20)
        for offset in range(0, len(data), 4096):
            data[offset] = 1
        child = os.fork()
        if child == 0:
            args = ["/usr/bin/prlimit", f"--as={SMALL}:{SMALL}", "--"]
            if use_time:
                args += ["/usr/bin/time", "-f", "%M", "-o", str(out / "time.txt")]
            args.extend(
                [
                    sys.executable,
                    "-IB",
                    str(Path(__file__).resolve()),
                    "image",
                    str(out / "proc.json"),
                ]
            )
            os.execve(args[0], args, {"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        _, status = os.waitpid(child, 0)
        os._exit(os.waitstatus_to_exitcode(status))
    _, status = os.waitpid(pid, 0)
    if os.waitstatus_to_exitcode(status):
        raise ValueError("synthetic subprocess did not close")
    return json.loads((out / "proc.json").read_text())


class PeakAfterExec(unittest.TestCase):
    def test_fresh_gnu_time_child(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for test in ["direct", "via_time"]:
                out = p / test
                out.mkdir()
                data = demonstrate(test == "via_time", out)
                self.assertLess(data["VmPeak_kib"], SMALL // 1024)
                self.assertEqual(data["rlimit_as_bytes"], [SMALL, SMALL])
                if test == "direct":
                    self.assertGreater(data["ru_maxrss_kib"], SMALL // 1024)
                else:
                    self.assertLess(int((out / "time.txt").read_text().strip()), SMALL // 1024)
                    self.assertLess(data["ru_maxrss_kib"], SMALL // 1024)

    def test_unchanged_image_limit_mandatory(self):
        snapshot = dict(rlimit_as_bytes=[usage.CAP] * 2, VmHWM_kib=100, VmPeak_kib=200)
        usage.check_image(snapshot)
        for bad in ({"rlimit_as_bytes": [usage.CAP, -1]}, {"VmPeak_kib": usage.CAP // 1024 + 1}):
            with self.assertRaises(ValueError):
                usage.check_image(snapshot | bad)


if __name__ == "__main__":
    if sys.argv[1:2] == ["image"]:
        usage.write(Path(sys.argv[2]), usage.memory())
    else:
        unittest.main()
