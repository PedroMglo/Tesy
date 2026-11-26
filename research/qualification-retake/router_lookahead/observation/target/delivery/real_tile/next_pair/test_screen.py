import tempfile
import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("screen.py")))


class TestSelector(unittest.TestCase):
    def test_eligibility_and_late_consumer(self):
        predicted = [[3, 2, 1, 0], [1, 2, 4, 5], [5, 4, 3, 0]]
        consumers = {1, 2} | {3}  # The last wave is still inside the scope.
        offers, unused = M["offer_result"](predicted, {0}, consumers)
        self.assertEqual((offers, unused), ([1, 2, 3, 4], [4]))
        data = [
            (1, offers, [], []),
            (2, offers, unused, ["L2/ffn_moe_out"]),
            (3, offers, unused, []),
            (4, offers, unused, []),
        ]
        src, log = M["first_candidate"](iter(data))
        self.assertEqual((src, len(log)), (3, 3))
        self.assertEqual(
            [r["reasons"] for r in log], [["all_offers_consumed"], ["missing_gold"], []]
        )
        self.assertIsNone(M["first_candidate"](data[:2])[0])

    def test_sealed_input_damage_is_terminal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a").write_bytes(b"lost")
            (root / "manifest.json").write_bytes(
                M["blob"]({"files": {"a": {"sha256": M["sha"](b"real"), "bytes": 4}}})
            )
            io = M["P"]["Inputs"](root)
            _, reader = M["archive"](io, root, M["sha"]((root / "manifest.json").read_bytes()))
            with self.assertRaisesRegex(ValueError, "digest"):
                reader("a")


if __name__ == "__main__":
    unittest.main()
