"""Wrong providers, stale policies and stray OFF journals must fail without a model."""

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

profile = run_path(str(Path(__file__).with_name("profile.py")))


class NumericAdmission(unittest.TestCase):
    def test_one_provider_may_change(self):
        name = profile["live"].static.SONAME
        pins = profile["LIBS"]
        old = {str(i): {"file": str(i), "sha256": str(i)} for i in range(17)}
        old[name] = {"file": "/original", "sha256": pins["original"]}
        new = old | {name: {"file": "/control", "sha256": pins["control"]}}
        check = profile["validate_maps"]
        check(old, new, Path("/control"), pins["control"])
        for wrong in (old, new | {"0": new["1"]}, new | {"extra": old[name]}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                check(old, wrong, Path("/control"), pins["control"])
        with self.assertRaises(ValueError):
            check(old, new, Path("/control"), pins["overlay"])

    def test_c55_expiry(self):
        start = datetime(2026, 11, 25, tzinfo=UTC)
        policy = {"snapshot": {"utc": start.isoformat()}}
        self.assertEqual(profile["c55_age"](policy, start + timedelta(seconds=3299)), 3299)
        for seconds in (-1, 3300):
            with self.assertRaises(ValueError):
                profile["c55_age"](policy, start + timedelta(seconds=seconds))

    def test_journal_is_exclusive_to_on(self):
        with TemporaryDirectory() as root:
            journal = Path(root, "phase.pfj1")
            check = profile["inspect_journal"]
            self.assertEqual(check(journal, False, {}, {}), {"enabled": False})
            journal.symlink_to(Path(root, "absent"))
            with self.assertRaises(ValueError):
                check(journal, False, {}, {})
            with self.assertRaises(ValueError):
                check(journal, True, {}, {})
