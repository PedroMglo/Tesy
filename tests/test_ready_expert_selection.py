import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).resolve().parents[1] / "research/ready-experts/selection.py"))


class CausalPlacement(unittest.TestCase):
    def test_publication_changes_only_future_offers(self):
        bank = S["PublicationBank"](1)
        a, b = (0, 1), (0, 2)
        bank.offer(a)
        bank.offer(b)
        self.assertEqual(set(bank.held), {b})
        bank.published(a, 100)
        self.assertEqual(set(bank.held), {b})
        bank.offer(a)
        bank.offer(b)
        self.assertEqual(set(bank.held), {a})
        self.assertEqual(bank.receipt()["rejected"], 1)
        self.assertEqual(bank.receipt()["copies"]["CPU"], 3)

    def test_tie_and_duplicate_offer(self):
        bank = S["PublicationBank"](2)
        a, b, c = (0, 1), (0, 2), (25, 3)
        for key in (a, b, a, c):
            bank.offer(key)
        self.assertEqual(set(bank.held), {a, c})
        self.assertEqual(bank.receipt()["repeated"], 1)
        self.assertEqual(bank.receipt()["copies"], {"CPU": 2, "CUDA0": 1})
        with self.assertRaisesRegex(ValueError, "before reserve"):
            bank.published(a, -1)


if __name__ == "__main__":
    unittest.main()
