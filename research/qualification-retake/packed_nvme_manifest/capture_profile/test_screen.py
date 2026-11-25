import tempfile
import unittest
from pathlib import Path

from screen import CHAINS, SONAME, chain, verify_listing


class ClosureTests(unittest.TestCase):
    def test_native_map_checks_all_objects_and_single_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.so"
            new = root / "new.so"
            old.touch()
            new.touch()
            alias = root / SONAME
            alias.symlink_to(new)
            paths = {str(k): root / str(k) for k in range(17)}
            for path in paths.values():
                path.touch()
            paths[SONAME] = old
            sealed = {k: [str(p), str(p)] for k, p in paths.items()}
            cand = paths | {SONAME: alias}
            self.assertEqual(verify_listing(cand, sealed, alias, new)[SONAME], str(new))
            with self.assertRaisesRegex(ValueError, "wrong libllama provider"):
                verify_listing(paths, sealed, alias, new)
            with self.assertRaisesRegex(ValueError, "wrong provider"):
                verify_listing(cand | {"3": new}, sealed, alias, new)
            with self.assertRaisesRegex(ValueError, "census"):
                verify_listing(cand | {"extra": old}, sealed, alias, new)

    def test_exact_derivation_constructor_pair(self):
        first, second = CHAINS
        for d, c in CHAINS.items():
            chain(d, c)
        with self.assertRaisesRegex(ValueError, "crossed"):
            chain(first, CHAINS[second])
