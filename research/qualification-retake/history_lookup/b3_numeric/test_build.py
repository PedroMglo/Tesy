import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("b3_build", Path(__file__).with_name("build.py"))
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


class Bindings(unittest.TestCase):
    def test_real_order_and_interpreter(self):
        a = "(NEEDED) Shared library: [liba.so]\n(NEEDED) Shared library: [libb.so]\n"
        b = "(RUNPATH) Library runpath: [here]"
        p = "[Requesting program interpreter: /lib/ld.so]"
        correct = B.dynamic(a + b, p)
        self.assertEqual(correct["needed"], ["liba.so", "libb.so"])
        self.assertNotEqual(correct, B.dynamic("".join(reversed(a.splitlines(True))) + b, p))
        for dynamic, interp in [(a + b + b, p), (a + a + b, p), (a + b, "")]:
            with self.assertRaises(ValueError):
                B.dynamic(dynamic, interp)

    def test_no_unexpected_or_alternate_provider(self):
        class Files:
            def require(self, path, sha):
                if B.digest(path) != sha:
                    raise ValueError("content")
                return path.resolve()

        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "lib.so.1"
            p.write_bytes(b"shared")
            refs = {"lib.so": [str(p), str(p)]}
            objs = {"lib.so": {"sha256": B.digest(p), "file": p.name}}
            B.matched_closure({"lib.so": p}, refs, objs, Files())
            for links in ({}, {"lib.so": p, "extra": p}):
                with self.assertRaises(ValueError):
                    B.matched_closure(links, refs, objs, Files())
            alt = Path(temp) / "lib.other"
            alt.write_bytes(b"shared")
            with self.assertRaises(ValueError):
                B.matched_closure({"lib.so": alt}, refs, objs, Files())


if __name__ == "__main__":
    unittest.main()
