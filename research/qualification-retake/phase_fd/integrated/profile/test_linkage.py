import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import linkage
from smoke import waiting_on_fifo


class LinkageChecks(unittest.TestCase):
    def test_only_child_ldd_receives_explicit_search(self):
        search = linkage.search_from_args(
            [
                "--env",
                "LD_LIBRARY_PATH=/private:/control",
                "--",
                "exe",
                "--env",
                "LD_LIBRARY_PATH=/bad",
            ]
        )
        with patch.object(linkage.subprocess, "check_output", return_value="") as actual:
            linkage.child_ldd(search)(Path("/exe"), Path("/backend"))
        self.assertEqual(actual.call_args.args[0], ["/usr/bin/ldd", Path("/exe")])
        self.assertEqual(
            actual.call_args.kwargs["env"],
            {"LD_LIBRARY_PATH": search, "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
        with self.assertRaises(ValueError):
            linkage.search_from_args(
                ["--env", "LD_LIBRARY_PATH=/a", "--env", "LD_LIBRARY_PATH=/a", "--"]
            )

    def test_external_dso_must_be_same_image_at_same_location(self):
        expected = {"/private/libllama.so.0.0.9884": "x", "libggml.so.0": "z"}
        self.assertEqual(
            linkage.numeric_census(expected, dict(expected))["libllama.so.0.0.9884"], "x"
        )
        for foreign in (
            {"libllama.so.0.0.9884": "x", "libggml.so.0": "z"},
            {"libggml.so.0": "z"},
            expected | {"/rogue/libextra.so": "y"},
        ):
            with self.assertRaises(ValueError):
                linkage.numeric_census(expected, foreign)

    def test_wait_witness_before_model(self):
        with (
            patch("smoke.Path.iterdir", return_value=[Path("/proc/2/fd/4")]),
            patch("smoke.os.readlink", return_value="/tmp/inputs.pipe"),
        ):
            waiting_on_fifo(2, Path("/tmp/inputs.pipe"))
        with (
            patch("smoke.Path.iterdir", return_value=[Path("/proc/2/fd/4")]),
            patch("smoke.os.readlink", return_value="/tmp/model.gguf"),
        ):
            with self.assertRaisesRegex(ValueError, "model descriptor"):
                waiting_on_fifo(2, Path("/tmp/inputs.pipe"))
