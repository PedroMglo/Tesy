import struct
import unittest

import run


class ReviewTests(unittest.TestCase):
    def setUp(self):
        n = 5
        ranks = [(r * 5 + k * 3) % 16 for r in range(n) for k in range(4)]
        slots = [(e * 7 + 3) % 40 for e in ranks]
        self.raw = struct.pack("<20i20i20f", *ranks, *slots, *([0.25] * 20))
        self.meta = dict(
            mode="ON",
            rows=n,
            hits=len(set(ranks)),
            splits=1,
            graph="GET_ROWS,CONT",
            entries=1,
            forwarded=1,
            remaps=1,
            threads=8,
            different=0,
            start=100,
            ready=110,
            consumer=120,
            resolution=1,
            min_tick=5,
        )

    def test_measurement_and_no_resolution(self):
        self.assertEqual(run.verdict("ON", 5, self.raw, self.meta)["ready_to_remap_ns"], 10)
        self.assertFalse(run.verdict("ON", 5, self.raw, {**self.meta, "ready": 120})["resolved"])

    def test_wrong_stride_and_outputs(self):
        wrong = {**self.meta, "mode": "WRONG", "different": 1}
        self.assertIsNotNone(run.verdict("WRONG", 5, self.raw, wrong, (self.raw, wrong["graph"])))
        for kw in ({"different": 0}, {"remaps": 0}, {"forwarded": 2}, {"consumer": 108}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                run.verdict("WRONG", 5, self.raw, {**wrong, **kw})
        with self.assertRaises(ValueError):
            run.verdict("ON", 5, self.raw, self.meta, (b"other", self.meta["graph"]))

    def test_off(self):
        off = {**self.meta, "mode": "OFF", "start": 0, "ready": 0, "consumer": 0}
        self.assertIsNone(run.verdict("OFF", 5, self.raw, off))
        with self.assertRaises(ValueError):
            run.verdict("OFF", 5, self.raw, {**off, "start": 1})
