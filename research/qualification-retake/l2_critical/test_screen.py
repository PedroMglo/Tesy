import unittest

from screen import ARENA, c295, eligible, maxima


def mark(k, e, s, g, call):
    return dict(kind=k, layer=0, expert=e, slot=s, gen=g, call=call)


def data():
    a, b, c = ((0, expert, expert, 1) for expert in range(3))
    jobs = {
        w: dict(read=r, copy=s, owner=1, order=i, begin=10, end=20)
        for i, (w, r, s) in enumerate(((a, 20, 4), (b, 5, 12), (c, 0, 22)))
    }
    group = dict(call=1, layer=0, pre=1, attention=2, after=3, wait=24, need=[a, b, c])
    return (jobs, [group], 4, 34, [], [], 0), a, b, c


class Critical(unittest.TestCase):
    def test_noncritical_hit_and_replacement_of_bottleneck(self):
        d, a, b, c = data()
        _, loss, _ = maxima(d, {b})
        self.assertEqual(loss["saved_wall_us"], 0)
        fixed, s, _ = maxima(d, {a, b})
        self.assertEqual(s["hit_worker_read_us"], 25)
        self.assertEqual(s["saved_wall_us"], 2)
        self.assertEqual(s["last_has_cold_read_after"], 1)
        self.assertEqual(s["changed_last_set"], 1)
        altered = {w: {**j, "read": 0 if w in {a, b} else j["read"]} for w, j in d[0].items()}
        for k in (0.8, 1, 1.2):
            self.assertAlmostEqual(
                c295.simulate((altered, *d[1:]), None, k, ARENA)["decode_us"], fixed + 22 * k
            )
            self.assertAlmostEqual(c295.simulate(d, None, k, ARENA)["decode_us"], fixed + 24 * k)

    def test_infinite_L2_starts_empty_and_waits_for_publication(self):
        rows = [
            mark(5, 4, 0, 1, 0),
            mark(10, 4, 0, 1, 0),
            mark(5, 4, 1, 2, 1),
            mark(10, 4, 1, 2, 1),
            mark(5, 6, 2, 1, 1),
            mark(10, 6, 2, 1, 1),
            mark(5, 6, 3, 3, 2),
            mark(10, 6, 3, 3, 2),
        ]
        self.assertEqual(eligible(rows), ({(0, 4, 1, 2), (0, 6, 3, 3)}, 3))
        with self.assertRaises(ValueError):
            eligible(rows[:1] + rows[2:])
        with self.assertRaises(ValueError):
            eligible(rows[:-1])

    def test_fail_shared_group_or_outstanding_or_missing(self):
        d, a, b, c = data()
        with self.assertRaises(ValueError):
            maxima((d[0], d[1] * 2, *d[2:]), {a})
        with self.assertRaises(ValueError):
            maxima((*d[:4], [a], [], 0), set())
        with self.assertRaises(ValueError):
            maxima((d[0], [], *d[2:]), set())


if __name__ == "__main__":
    unittest.main()
