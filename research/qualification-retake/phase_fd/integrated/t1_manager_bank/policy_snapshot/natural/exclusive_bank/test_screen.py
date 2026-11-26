import itertools
import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("screen.py")))
Bank = M["Bank"]


class BankTests(unittest.TestCase):
    def test_boundary_promotion_then_disk_lru(self):
        a, b, c, d, e = [(0, n) for n in range(5)]
        bank = Bank(3, [b, a, c], [a, d])
        self.assertEqual(list(bank.lru), [b, c])
        self.assertEqual(bank.reserve(b, a), (True, None))
        self.assertEqual(list(bank.lru), [c, a])
        self.assertEqual(bank.reserve(e, d), (False, None))
        self.assertEqual(list(bank.lru), [c, a, d])
        f = (2, 15)
        self.assertEqual(bank.reserve(f, e), (False, c))
        self.assertEqual(list(bank.lru), [a, d, e])
        self.assertTrue(bank.primary.isdisjoint(bank.lru))
        self.assertEqual(bank.peak, 3)
        with self.assertRaisesRegex(ValueError, "resident"):
            bank.reserve(b, f)

    def test_exhaustive_transfers_and_publication_order(self):
        for incoming in itertools.product(range(4), repeat=4):
            bank = Bank(2, [2, 3], [0, 1])
            primary = [0, 1]
            lru = [2, 3]
            outstanding = []
            for i, e in enumerate(incoming):
                if e in primary:
                    continue
                s = i % 2
                old = primary[s]
                primary[s] = e
                hit = e in lru
                if hit:
                    lru.remove(e)
                drop = lru.pop(0) if len(lru) == 2 else None
                lru.append(old)
                self.assertEqual(bank.reserve(e, old), (hit, drop))
                outstanding.append((e, old))
            # Completions acknowledge already staged bytes. They never drive the LRU.
            for order in (outstanding, list(reversed(outstanding))):
                self.assertCountEqual(order, outstanding)
                self.assertEqual(list(bank.lru), lru)
                self.assertEqual(bank.primary, set(primary))

    def test_empty_and_impossible_victim(self):
        b = Bank(1, [(1, 2)], [])
        self.assertEqual(b.reserve((1, 2), None), (True, None))
        self.assertFalse(b.lru)
        with self.assertRaisesRegex(ValueError, "victim owner"):
            b.reserve((0, 2), (8, 3))
        with self.assertRaisesRegex(ValueError, "capacity"):
            Bank(1, [1, 2], [])

    def test_read_unobserved_and_set_charge(self):
        p = {
            "jobs": [
                dict(
                    ordinal=0, expert=4, slot=0, generation=2, source="disk", r0_same_site_set_ns=8
                ),
                dict(
                    ordinal=1,
                    expert=5,
                    slot=3,
                    generation=3,
                    source="bank",
                    r0_same_site_set_ns=None,
                ),
            ]
        }
        raw = {"jobs": [dict(ordinal=0, read_spans_ns=[(4, 15)])]}

        def costs(*args):
            return {"common_set_floor": 19}, None

        j = [(4, 0, 2, False, True), (5, 3, 3, True, False)]
        self.assertEqual(M["clock_group"](p, raw, j, costs), (19, 8, 1, 1))
        j[0] = (4, 0, 4, False, True)
        with self.assertRaisesRegex(ValueError, "identity"):
            M["clock_group"](p, raw, j, costs)


if __name__ == "__main__":
    unittest.main()
