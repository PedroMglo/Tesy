import itertools
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from history_lookup import screen as s  # noqa: E402


class Lookup(unittest.TestCase):
    def test_first_output_excludes_anchor_and_prevents_overlapping_copy(self):
        self.assertEqual(s.matches([], [9, 9, 9, 9]), [(1, 0), (2, 0), (1, 0)])
        self.assertEqual(s.matches([4, 5], [8, 4, 5, 9])[0], (2, 0))

    def test_exhaustive_histories_and_partitions(self):
        for seq in itertools.product((0, 1), repeat=6):
            prompt, token = list(seq[:1]), list(seq[1:])
            actions = []
            for i in range(4):
                prior = prompt + token[: i + 1]
                future = token[i + 1 :]
                n = max(
                    [0]
                    + [
                        length
                        for length in range(1, min(7, len(future)) + 1)
                        if any(
                            prior[j : j + length] == future[:length]
                            for j in range(len(prior) - length + 1)
                        )
                    ]
                )
                actions.append(n)
            rows = s.matches(prompt, token)
            self.assertEqual([n for n, _ in rows], actions)

            def brute(i, allow_ar, actions=actions):
                if i == 4:
                    return 0
                opts = [
                    4 + brute(j, allow_ar) for j in range(i + 1, min(4, i + 1 + actions[i]) + 1)
                ]
                if allow_ar:
                    opts.append(2 + brute(i + 1, allow_ar))
                return min(opts)

            for only in (True, False):
                cost, path = s.optimize(rows, 2, 4, only)
                self.assertEqual(cost, brute(0, not only))
                self.assertEqual(s.verify_path(path, prompt, token, 2, 4), cost)

    def test_skip_earlier_match_to_reach_a_better_block(self):
        rows = [(1, 0), (3, 1), (0, None), (0, None), (0, None)]
        cost, path = s.optimize(rows, 1, 2.5)
        self.assertEqual(cost, 3.5)
        self.assertEqual(
            [(a["p"], a["q"], a["action"]) for a in path], [(0, 1, "AR"), (1, 5, "B8")]
        )

    def test_wrong_witness_and_short_final_block(self):
        prompt, tokens = [1, 2], [7, 1, 2]
        cost, path = s.optimize(s.matches(prompt, tokens), 1, 5, True)
        self.assertEqual(cost, 5)
        self.assertEqual(s.verify_path(path, prompt, tokens, 1, 5), cost)
        for bad_source in (2, 3, 4):
            with self.subTest(bad_source=bad_source), self.assertRaises(ValueError):
                s.verify_path([{**path[0], "source": bad_source}], prompt, tokens, 1, 5)

    def test_missing_private_manifest_member(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            s.raw_summaries(Path(tmp), {"files": 1})


if __name__ == "__main__":
    unittest.main()
