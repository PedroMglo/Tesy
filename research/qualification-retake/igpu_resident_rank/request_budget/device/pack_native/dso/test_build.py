import unittest
from pathlib import Path
from runpy import run_path

BUILD = run_path(Path(__file__).with_name("build.py"))


class PrivateLink(unittest.TestCase):
    def setUp(self):
        self.destination = Path("/private")
        self.args = [
            "/usr/bin/c++",
            "-shared",
            "-Wl,--dependency-file=CMakeFiles/llama.dir/link.d",
            "-o",
            "../bin/" + BUILD["IMAGE"],
            "CMakeFiles/llama.dir/llama-context.cpp.o",
            "CMakeFiles/llama.dir/llama-moe-stream.cpp.o",
            "CMakeFiles/llama.dir/other.o",
        ]

    def test_only_two_objects_move_and_no_original_output(self):
        intact = BUILD["link"](self.args, self.destination, ())
        cand = BUILD["link"](self.args, self.destination, BUILD["TUS"])
        self.assertEqual([x for x, y in zip(intact, cand, strict=True) if x != y], self.args[5:7])
        self.assertEqual(intact[2], "-Wl,--dependency-file=/private/link.d")
        self.assertEqual(intact[4], str(self.destination / BUILD["IMAGE"]))

    def test_ambiguous_output_rejected(self):
        for args in (self.args + ["-o", "oops"], self.args + [self.args[2]], self.args[:-2]):
            with self.assertRaises(ValueError):
                BUILD["link"](args, self.destination, BUILD["TUS"])


if __name__ == "__main__":
    unittest.main()
