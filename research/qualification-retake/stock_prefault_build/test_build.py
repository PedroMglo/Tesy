import unittest
from pathlib import Path

from build import CALL, DSO, OBJ, link_argv, patch


class Build(unittest.TestCase):
    def test_source_anchor_and_rejection(self):
        text = "#include <cstring>\n" + CALL
        changed = patch(text)
        self.assertIn('std::strcmp(lazy, "1")', changed)
        self.assertIn("!lazy || lazy[0] == '0'", changed)
        with self.assertRaises(ValueError):
            patch(changed)
        with self.assertRaises(ValueError):
            patch(text + "\n" + CALL)

    def test_link_never_writes_source(self):
        cmd = [
            ":",
            "&&",
            "/usr/bin/g++-15",
            "-Wl,--dependency-file=src/CMakeFiles/llama.dir/link.d",
            "-o",
            "bin/" + DSO,
            OBJ,
            *[f"existing{i}.o" for i in range(43)],
            "&&",
            ":",
        ]
        dest = Path("/tmp/tesy-private-synthetic")
        args = link_argv(cmd, dest)
        self.assertEqual(args[args.index("-o") + 1], str(dest / DSO))
        self.assertIn("-Wl,--dependency-file=" + str(dest / "link.d"), args)
        self.assertIn(str(dest / "llama-model.cpp.o"), args)
        with self.assertRaises(ValueError):
            link_argv([s for s in cmd if s != OBJ], dest)


if __name__ == "__main__":
    unittest.main()
