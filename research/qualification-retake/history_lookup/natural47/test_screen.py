import unittest

from screen import cases


class TestWitnessConstruction(unittest.TestCase):
    def test_keeps_aliases_and_channel_alternatives(self):
        texts = ("<|channel|>", "analysis", "<|message|>", "<|end|>", "<|start|>",
                 "assistant", "final", "commentary", "<|return|>", "x", "y")
        pieces = {i: (3 if s.startswith("<|") else 1, s.encode()) for i, s in enumerate(texts)}
        pieces[11] = (1, b"final")
        for c, expected in [("final", 2), ("commentary", 1)]:
            seq = list(cases(pieces, ["x"] * 35, ["y"] * 2, c))
            self.assertEqual(len(seq), expected)
            self.assertTrue(all(len(ids) == 47 for ids in seq))
        # A non-authoritative projection spanning UTF-8, a delimiter or two samples is never filled
        # by greedily splitting a delta to force the desired number of IDs.
        for missing in ("xy", "<|message|>y", "é"):
            self.assertFalse(list(cases(pieces, ["x"] * 35, ["y", missing], "final")))

    def test_multi_piece_or_wrong_frame_count_stays_unqualified(self):
        with self.assertRaisesRegex(ValueError, "width"):
            list(cases({}, ["x"] * 34, ["y"] * 2, "final"))
