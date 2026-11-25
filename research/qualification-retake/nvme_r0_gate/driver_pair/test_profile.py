"""No device enumeration, DSOs or GPU required."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "tesymixedprofile", Path(__file__).with_name("profile.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TestIdentity(unittest.TestCase):
    def test_linker_list(self):
        self.assertEqual(
            m.dependency_paths(
                "linux-vdso.so.1 (0x45)\n libx.so.1 => /a/x.so.1 (0xaa)\n /x/ld.so (0x19)"
            ),
            {"libx.so.1": "/a/x.so.1", "ld.so": "/x/ld.so"},
        )
        for bad in ("x => not found", "linux-vdso.so.1 (0xaa)", "x => /a (0x1)\nx => /b (0x2)"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                m.dependency_paths(bad)

    def test_actual_loader_init_is_pid_specific(self):
        with tempfile.TemporaryDirectory() as root:
            lib = Path(root) / "libx"
            lib.touch()
            actual = m.initialized(f"  153: calling init: {lib}\n 153: calling fini: /z", 153)
            m.required_present(actual, [str(lib)])
            with self.assertRaisesRegex(ValueError, "missing runtime"):
                m.required_present(actual, [str(lib), "/z"])
            with self.assertRaises(ValueError):
                m.initialized(f"  154: calling init: {lib}", 153)
            with self.assertRaises(ValueError):
                m.initialized(f"  153: trying file={lib}", 153)

    def test_hash_once_per_inode_mutation_and_budget(self):
        with tempfile.TemporaryDirectory() as root:
            f = Path(root) / "file"
            f.write_bytes(b"abcd")
            alias = f.with_name("alias")
            os.link(f, alias)
            files = {}
            with (
                mock.patch.object(m, "MAX_READ", 4),
                mock.patch.object(m.hashlib, "file_digest", wraps=m.hashlib.file_digest) as calls,
            ):
                self.assertEqual(m.remember(f, files), m.remember(alias, files))
                self.assertEqual(calls.call_count, 1)
                more = f.with_name("more")
                more.write_bytes(b"e")
                with self.assertRaisesRegex(ValueError, "budget"):
                    m.remember(more, files)
                f.write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    m.check_records(files)
                with self.assertRaises(ValueError):
                    m.remember(f, files)

    def test_private_alias_and_output_size_charge(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root)
            driver = data / "outside"
            driver.write_bytes(b"d" * 20000)
            out = data / "output"
            folder = out / "driver"
            folder.mkdir(parents=True)
            link = folder / "libcuda.so.1"
            link.symlink_to(driver)
            args = SimpleNamespace(new_output_dir=out, installed_driver=driver, libs=Path("/c269"))
            self.assertEqual(m.alias_check(args), link)
            self.assertEqual(m.output_bytes(out), len(os.fsencode(driver)))
            self.assertEqual(m.native_env(args, debug=True)["LD_LIBRARY_PATH"], f"/c269:{folder}")
            self.assertNotIn("LD_PRELOAD", m.native_env(args))
            (folder / "second").touch()
            with self.assertRaisesRegex(ValueError, "alias"):
                m.alias_check(args)

    def test_exclusive_result(self):
        with tempfile.TemporaryDirectory() as root:
            pos = Path(root) / "receipt.json"
            m.save(pos, {"v": 1})
            with self.assertRaises(FileExistsError):
                m.save(pos, {"v": 2})
            self.assertEqual(m.get_json(pos), {"v": 1})


if __name__ == "__main__":
    unittest.main()
