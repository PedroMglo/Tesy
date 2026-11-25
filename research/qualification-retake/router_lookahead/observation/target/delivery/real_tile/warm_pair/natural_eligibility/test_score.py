import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

S = run_path(str(Path(__file__).with_name("score.py")))
transition = S["transition"]


class SlotTest(unittest.TestCase):
    def event(self, kind=11, victim=2, gen=5, expert=7):
        return SimpleNamespace(kind=kind, a=victim, gen=gen, expert=expert)

    def test_empty_partial_full_replacement(self):
        for old_state in (0, 2):
            old = (-1 if old_state == 0 else 2, 4, old_state)
            new = transition(old, self.event(victim=old[0]))
            self.assertEqual(new, (7, 5, 1))
            self.assertEqual(transition(new, self.event(kind=17)), (7, 5, 2))
            for other_bound in (0, 1, 39):
                before = other_bound + (old_state != 0)
                after = other_bound + (new[2] != 0)
                self.assertGreaterEqual(after, before)
                self.assertEqual(after == 0, False)

    def test_bad_generation_victim_publication_and_overwrite(self):
        for old, event in (
            ((2, 4, 2), self.event(gen=6)),
            ((2, 4, 2), self.event(victim=3)),
            ((2, 4, 1), self.event()),
            ((2, 4, 2), self.event(kind=17)),
            ((2, 4, 1), self.event(kind=17, gen=4, expert=8)),
        ):
            with self.assertRaises(ValueError):
                transition(old, event)


if __name__ == "__main__":
    unittest.main()
