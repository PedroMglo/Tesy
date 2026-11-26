import struct
import sys
import tempfile
import unittest
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

with patch.object(sys, "path", sys.path.copy()):
    G = run_path(str(Path(__file__).with_name("grade.py")))
P = G["probes"]


class ProbeContract(unittest.TestCase):
    def test_names_shapes_and_unobservable_reference(self):
        sites = P.sites()
        prior = list(G["integrated"].cuts("ON"))
        self.assertEqual(len({n for _, n, _ in sites + prior}), 394)
        self.assertEqual(len(sites), 11)
        self.assertEqual(
            sum(12 * s.dims[0] * (s.dims[1] if len(s.dims) > 1 else 1) for _, _, s in sites), 337920
        )
        source = P.render().decode()
        for _, name, site in sites:
            self.assertEqual(source.count(f'cuts.emplace("{name}",cuts.at("{site.name}-0"))'), 1)
        self.assertIn("l25.cuts.size()==394", source)
        self.assertIn("observed.size()==cuts.size()", source)
        with self.assertRaises(ValueError):
            G["base"].validate_words(struct.pack("<f", float("nan")) * 2880, sites[0][2])

    def test_observer_change_blocks_attribution(self):
        G["paired_subset"]({"core": "ok"}, {"core": "ok", "new": "x"})
        for damaged in ({}, {"core": "wrong"}):
            with self.assertRaises(ValueError):
                G["paired_subset"]({"core": "ok"}, damaged)
        self.assertEqual(G["inference"](0, 37), "DIFFERENT_PRODUCT_WITH_IDENTICAL_INPUT")
        self.assertEqual(G["inference"](3, 37), "DIFFERENT_INPUT_AT_ROUTER")
        self.assertEqual(G["inference"](3, 0), "DIFFERENT_INPUT_AT_ROUTER")

    def test_missing_and_repeated_stops_fail(self):
        site = P.sites()[0]
        source = f"189\t3\t{site[1]}\tMUL\t2880\t3\t1\t1\t4\t11520\t34560\t34560\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for lines in ("", source + source, source.replace("2880", "2879", 1)):
                (root / "geometry.tsv").write_text(lines)
                with self.assertRaises(ValueError):
                    G["base"].check_geometry(root, "B3", [site])
            (root / "geometry.tsv").write_text(source)
            G["base"].check_geometry(root, "B3", [site])


if __name__ == "__main__":
    unittest.main()
