"""Causality and cutoff checks using explicit three-call synthetic journals."""

import struct
import unittest

from scores import describe, freeze_tables


def journal(decode_ids, first_cut=b"P"):
    chunks = [b"TPR1"]
    for call, ids in enumerate(((12, 13, 14, 15), (8, 9, 10, 11), decode_ids), 1):
        chunks.extend(
            (b"C", struct.pack("<HH", call, 1), b"U", struct.pack("<HBHB", 1, 1, call - 1, 1))
        )
        for layer in range(36):
            chunks.extend((b"R", bytes((layer, ord("S"), 1, *ids))))
        chunks.extend((b"ED", (first_cut, b"I", b"F")[call - 1]))
    return b"".join(chunks)


class CausalScores(unittest.TestCase):
    def test_future_rows_never_enter_cut(self):
        args = (1, 1, 1, 1)
        snap = freeze_tables(journal((4, 5, 6, 7)), *args)
        self.assertEqual(snap, freeze_tables(journal((0, 1, 2, 3)), *args))
        self.assertEqual(snap["P"][0][8:16], [0] * 4 + [1] * 4)
        self.assertEqual(snap["I"][35][8:16], [1] * 8)
        self.assertEqual(
            describe(snap["I"])["layers"][35]["top40_by_score_then_id"][:8], list(range(8, 16))
        )

    def test_bad_cut_or_terminal_fails(self):
        valid = journal((1, 2, 3, 4))
        for raw, args in [(valid[:-1], (1, 1, 1, 1)), (valid, (2, 1, 1, 1)), (valid, (1, 2, 1, 1))]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                freeze_tables(raw, *args)
