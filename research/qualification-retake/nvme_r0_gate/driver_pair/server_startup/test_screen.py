import tempfile
import unittest
from pathlib import Path

import screen


class Startup(unittest.TestCase):
    def test_loader_is_exact(self):
        good = ("linux-vdso.so.1 (0x10)\nliba.so => /b/liba.so (0x89)\n"
                "/lib64/ld-linux-x86-64.so.2 (0xab)")
        self.assertEqual(screen.interpret(good)["liba.so"], Path("/b/liba.so"))
        for bad in (
            good.replace("=> /b/liba.so (0x89)", "=> not found"),
            good.replace("/b/", "../b/"),
            good + "\nliba.so => /b/liba.so (0xaa)",
            good.split("\n", 1)[1],
            good + "\n/else.so (0x1)",
        ):
            with self.assertRaises(ValueError):
                screen.interpret(bad)

    def test_monitor_and_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left, right = root / "backend", root / "driver"
            left.mkdir()
            right.mkdir()
            alias = right / "libcuda.so.1"
            alias.symlink_to(root / "sealed")
            screen.first_alias(alias.name, [left, right], alias)
            self.assertEqual(
                screen.environment([left, right]),
                dict(PATH="/usr/bin:/bin", LC_ALL="C", LD_LIBRARY_PATH=f"{left}:{right}"),
            )
            (left / alias.name).symlink_to(root / "different")
            with self.assertRaisesRegex(ValueError, "first provider"):
                screen.first_alias(alias.name, [left, right], alias)

    def test_digest_cache_checks_identity_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "lib.so"
            p.write_bytes(b"first")
            files = screen.Files()
            h = screen.digest(b"first")
            files.require(p, h)
            files.require(p, h)
            self.assertEqual(files.size, 5)
            p.write_bytes(b"second")
            with self.assertRaises(ValueError):
                files.require(p, h)


if __name__ == "__main__":
    unittest.main()
