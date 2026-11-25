import importlib.util
import unittest
from pathlib import Path


def load():
    spec = importlib.util.spec_from_file_location(
        "phase_build", Path(__file__).with_name("build.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = load()


class BuildTest(unittest.TestCase):
    def tokens(self):
        return [
            ":",
            "&&",
            B.CXX,
            "-shared",
            "-Wl,--dependency-file=src/CMakeFiles/llama.dir/link.d",
            "-o",
            "bin/" + B.IMAGE,
            *map(B.obj, B.SOURCES),
            "other.o",
            "&&",
            ":",
        ]

    def test_only_private_outputs(self):
        raw = self.tokens()
        private = B.link_args(raw, Path("/private"))
        self.assertIn("other.o", private)
        self.assertIn("/private/" + B.IMAGE, private)
        for name in B.SOURCES:
            self.assertNotIn(B.obj(name), private)
            self.assertIn("/private/" + Path(B.obj(name)).name, private)
        self.assertEqual(raw, self.tokens())

    def test_duplicate_or_absent_obj(self):
        raw = self.tokens()
        raw.remove(B.obj(B.CTX))
        for tokens in (raw, self.tokens()[:-2] + [B.obj(B.MGR), "&&", ":"]):
            with self.assertRaises(ValueError):
                B.link_args(tokens, Path("/private"))

    def test_old_exports(self):
        old = {"data": ["B", "40"], "fn": ["T", None]}
        self.assertEqual(B.abi_subset(old, old | {"new": ["W", None]}), ["new"])
        for value in ({}, old | {"data": ["B", "20"]}, old | {"fn": ["D", None]}):
            with self.assertRaises(ValueError):
                B.abi_subset(old, value)


if __name__ == "__main__":
    unittest.main()
