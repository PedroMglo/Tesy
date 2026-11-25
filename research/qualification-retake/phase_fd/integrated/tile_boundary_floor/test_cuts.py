import unittest
from pathlib import Path
from runpy import run_path

api = run_path(str(Path(__file__).with_name("cuts.py")))


class CutTests(unittest.TestCase):
    def test_number_of_independent_layer_changes(self):
        count = api["fewest_layers"]
        self.assertEqual(count([8, 6, 5], [7, 2, 3], 19), 0)
        self.assertEqual(count([8, 6, 5], [7, 2, 3], 15), 1)
        self.assertEqual(count([8, 6, 5], [7, 2, 3], 12), 3)
        self.assertIsNone(count([8, 6, 5], [7, 2, 3], 11))


if __name__ == "__main__":
    unittest.main()
