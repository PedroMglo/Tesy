import unittest

import screen


class CausalPair(unittest.TestCase):
    def test_latest_copy_fully_before_sampled(self):
        history = (99, 1, 2, 3, 4, 11, 1, 2, 8, 9, 12, 1, 2)
        self.assertEqual(screen.draft(history, 2, 2), (8, 9))
        shortened = (99, 1, 2, 3, 4, 11, 1, 2)
        self.assertEqual(screen.draft(shortened, 2, 2), (3, 4))
        self.assertEqual(
            screen.draft((1, 2, 3, 4, 11, 1, 2), 2, 2), ()
        )  # Native skips index zero.

    def test_reject_and_first_eog(self):
        prompt = (99, 1, 2, 3, 4, 11, 1)
        accept = screen.replay(prompt, (2, 3, 4), 2, 2)
        self.assertEqual(
            (
                accept["calls"],
                accept["accepted_ids"],
                accept["ordinary_corrective_or_bonus"],
            ),
            (1, 2, 0),
        )
        reject = screen.replay(prompt, (2, 90), 2, 2)
        self.assertEqual(
            (reject["calls"], reject["rejections"], reject["fewer_calls"]), (1, 1, 0)
        )
        end = screen.replay(prompt, (2,), 2, 2)
        self.assertEqual(end["outputs"], 0)
