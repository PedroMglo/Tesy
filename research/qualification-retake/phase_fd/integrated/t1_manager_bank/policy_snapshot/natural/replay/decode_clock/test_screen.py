import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

m = run_path(Path(__file__).with_name("screen.py"))


class DecodeService(unittest.TestCase):
    def test_per_site_identity_origin_and_destination(self):
        a, b = (4, 1, 0, -1), (5, 1, 0, -1)
        jobs = {a: {11: (3, 2), 15: (1, 1)}, b: {11: (4, 3)}}
        obs = {a: {11: (2, 1, 20, 5)}, b: {15: (1, 1, 40, 2)}}
        bank = [{11}] + [set() for _ in range(35)]
        bases = [[(0, m["PAYLOAD"] // 3)] * 3 for _ in bank]
        fixed, counts = m["price"](jobs, obs, bank, bases, 5, False)
        self.assertEqual(fixed, 5)
        self.assertEqual(counts["all"]["common_jobs"], 1)
        self.assertEqual(counts["all"]["new_jobs"], 2)
        self.assertEqual(counts["all"]["disk_jobs"], 1)
        self.assertEqual(counts["all"]["host_bank_jobs"], 2)
        self.assertEqual(m["price"](jobs, obs, bank, bases, 5, True)[0], 0)
        bank[0].clear()
        self.assertEqual(m["price"](jobs, obs, bank, bases, 4, False)[0], 21)
        self.assertEqual(m["price"](jobs, obs, bank, bases, 0, False)[0], 5)

    def test_four_workers_do_not_sum_to_barrier(self):
        self.assertEqual(m["lower"]([5, 5, 5, 5]), 20)
        self.assertEqual(m["lower"]([5, 5, 5, 5, 5]), 25)
        self.assertEqual(m["lower"]([8, 2, 1, 0]), 32)

    def test_same_worker_three_pairs_before_return(self):
        site = (10, 1, 5, -1)

        def row(kind, i, worker=1, component=-1):
            return SimpleNamespace(
                call=10,
                tile=1,
                layer=5,
                wave=-1,
                expert=4,
                slot=2,
                gen=1,
                kind=kind,
                ns=i * 10,
                begin=i * 10 - 3,
                a=0,
                worker=worker,
                component=component,
            )

        seq = [row(9, 1), row(11, 2), row(12, 3), row(13, 4), row(19, 5)]
        seq.extend(row(k, i + 6, component=i // 2) for i, k in enumerate([15, 16] * 3))
        seq.extend([row(17, 12), row(20, 13), row(23, 14)])
        self.assertEqual(m["measurements"](seq, {site: {4: (2, 1)}})[site][4], (2, 1, 9, 9))
        seq[7].worker = 3
        with self.assertRaises(ValueError):
            m["measurements"](seq, {site: {4: (2, 1)}})
        seq[7].worker = 1
        seq[7].component = 2
        with self.assertRaises(ValueError):
            m["measurements"](seq, {site: {4: (2, 1)}})


if __name__ == "__main__":
    unittest.main()
