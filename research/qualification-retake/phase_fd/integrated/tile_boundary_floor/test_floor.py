import unittest
from pathlib import Path
from runpy import run_path

api = run_path(str(Path(__file__).with_name("floor.py")))
floor = api["compulsory"]


class BoundaryTests(unittest.TestCase):
    def test_grants_entry_loading_bank_and_charges_unrequested_restoration(self):
        self.assertEqual(floor({1, 2, 3}, {1, 4, 5}, {1}, {2}, {3, 4}), {5})

    def test_preserving_an_intermediate_cut_can_force_a_reread(self):
        first = floor({1, 2}, {2}, {1}, set(), set())
        second = floor({1}, {1}, {2}, set(), set())
        merged = floor({1, 2}, {1}, {1}, set(), set())
        self.assertEqual((first, second, merged), ({2}, {1}, {2}))


if __name__ == "__main__":
    unittest.main()
