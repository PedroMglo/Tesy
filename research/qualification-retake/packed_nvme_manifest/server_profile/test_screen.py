import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen  # noqa: E402


class ServerMapTests(unittest.TestCase):
    def test_all_consumers_even_extra_and_duplicate(self):
        text = " 0x0000000000000001 (NEEDED)             Shared library: [libllama.so.0]"
        self.assertEqual(screen.needed(text), [screen.SONAME])
        self.assertEqual(screen.needed(text.replace("NEEDED", "SONAME")), [])
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            screen.needed(text + "\n" + text)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            screen.needed(text.replace(screen.SONAME, "/wrong/alias"))

    def test_standalone_map_can_be_subset_but_all_entries_must_be_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = (root / "old", root / "new")
            old.touch()
            new.touch()
            alias = root / screen.SONAME
            alias.symlink_to(new)
            r = {str(i): root / str(i) for i in range(23)}
            for p in r.values():
                p.touch()
            r[screen.SONAME] = old
            sealed = {k: [str(p), str(p)] for k, p in r.items()}
            cand = r | {screen.SONAME: alias}
            partial = {screen.SONAME: alias, "0": r["0"]}
            self.assertEqual(
                set(screen.validate_map(partial, sealed, alias, new, entire=False)), set(partial)
            )
            with self.assertRaisesRegex(ValueError, "full-program"):
                screen.validate_map(partial, sealed, alias, new, entire=True)
            with self.assertRaisesRegex(ValueError, "foreign isolated"):
                screen.validate_map(partial | {"another": old}, sealed, alias, new, entire=False)
            screen.check_wrong_provider(cand, sealed, old, old)
            with self.assertRaisesRegex(ValueError, "foreign libllama accepted"):
                screen.check_wrong_provider(cand, sealed, alias, new)


if __name__ == "__main__":
    unittest.main()
