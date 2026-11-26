import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class ObserverTest(unittest.TestCase):
    def test_callback_transport_and_ranks(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            shutil.copyfile(HERE / "control_api.h", path / "lookahead.h")
            subprocess.run(
                [
                    "/usr/bin/c++",
                    "-std=c++17",
                    "-O3",
                    "-I",
                    d,
                    str(HERE / "controls.cpp"),
                    "-o",
                    str(path / "controls"),
                ],
                check=True,
                timeout=25,
            )
            subprocess.run([str(path / "controls")], check=True, timeout=5)
