"""Synthetic loader log and paths only. Never opens the GPU."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "tesy_origin", Path(__file__).with_name("driver_origin.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OriginTest(unittest.TestCase):
    def setUp(self):
        self.providers = {n: Path("/signed") / n for n in m.ORDER}
        self.core = {str(self.providers[n]) for n in m.ORDER[:2]}

    def test_known_optional_absence_and_full_init(self):
        selected = m.validate_driver_log({*m.ORDER[:2], m.ABSENT}, self.core, self.providers)
        self.assertEqual(selected[m.ABSENT], {"requested": True, "initialized": False})
        self.assertFalse(selected[m.ORDER[2]]["initialized"])
        all_live = {str(v) for v in self.providers.values()}
        self.assertTrue(
            all(
                m.validate_driver_log(set(m.ORDER), all_live, self.providers)[k]["initialized"]
                for k in m.ORDER
            )
        )

    def test_same_bytes_on_other_path_is_foreign(self):
        with self.assertRaises(ValueError):
            m.validate_driver_log(
                set(m.ORDER[:3]), self.core | {"/rpm/" + m.ORDER[2]}, self.providers
            )

    def test_optional_lookup_must_resolve_and_unknowns_fail(self):
        for queries, libs in (
            (set(m.ORDER), self.core),
            ({"libnvidia-x"}, self.core),
            (set(), self.core | {"/system/" + m.ABSENT}),
            (set(), set()),
            (set(), self.core | {"/system/libnv-new.so.0"}),
        ):
            with self.subTest(queries=queries), self.assertRaises(ValueError):
                m.validate_driver_log(queries, libs, self.providers)

    def test_parser_keeps_every_requested_provider(self):
        stream = "".join(
            f" 12: find library={n} [0]; searching\n"
            for n in [*m.ORDER, m.ABSENT, "libcudart.so.13"]
        )
        self.assertEqual(m.requests(stream, 12), set(m.ORDER) | {m.ABSENT})
        self.assertIn("libcudart.so.13", m.all_requests(stream, 12))
        with self.assertRaises(ValueError):
            m.all_requests(stream, 13)


if __name__ == "__main__":
    unittest.main()
