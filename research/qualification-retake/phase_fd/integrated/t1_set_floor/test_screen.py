import importlib.util
import itertools
import unittest
from pathlib import Path

sp = importlib.util.spec_from_file_location(
    "set_floor_oracle", Path(__file__).with_name("screen.py")
)
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)


def brute(groups, allow, a, b):
    ids = sorted({job.key for g in groups for job in g if job.first and job.key in allow})

    def price(chosen):
        score = 0
        for g in groups:
            terms = [
                b * j.copies + (a * j.read if j.first and j.key not in chosen else 0) for j in g
            ]
            score += max(sum(terms), 4 * max(terms))
        return score

    return [min(price(s) for s in itertools.combinations(ids, k)) for k in range(1 + len(ids))]


def row(kind, ns, **fields):
    values = {key: 0 for key in m.src.fd.Row._fields}
    values.update(
        kind=kind, ns=ns, call=1, tile=1, layer=0, wave=0, slot=0, gen=1, expert=2, worker=1
    )
    return m.src.fd.Row(**(values | fields))


def valid():
    t = 2_000_001
    records = [row(9, t), row(11, t + 1), row(12, t + 2, a=0), row(10, t + 3), row(19, t + 4)]
    meta = {}
    for i in range(3):
        t += 30
        meta[0, i] = (4096 * i, 16)
        records.append(row(15, t + 10, begin=t, component=i, a=4096 * i, b=4096, c=4096))
        records.append(row(16, t + 15, begin=t + 10, component=i, a=16, b=0))
    records.extend([row(17, t + 18), row(20, t + 19), row(23, t + 20)])
    plan = [{"site": [1, 1, 0, 0], "experts": [dict(expert=2, slot=0, generation=1)]}]
    return records, plan, meta


class ReadAndSet(unittest.TestCase):
    def test_global_exact_all_cardinalities(self):
        for seed in range(7):
            groups = [
                [
                    m.Job(
                        (layer, i),
                        1 + (i * 9 + 2 * layer + seed) % 13,
                        (i * 5 + seed * 4) % 17,
                        i % 4 != 3,
                    )
                    for i in range(n)
                ]
                for layer, n in enumerate([6, 2])
            ]
            can = {j.key for g in groups for j in g if (j.key[1] + seed) % 5 != 0}
            for a, b in ((1, 1), (4, 5)):
                frontier, choose = m.solve(groups, can, a, b)
                self.assertEqual(frontier, brute(groups, can, a, b))
                for k in range(len(frontier)):
                    self.assertEqual(len(choose(k)), k)
                    self.assertEqual(sum(m.bounds(g, choose(k), a, b) for g in groups), frontier[k])
        j = m.Job((0, 5), 1, 0, True)
        with self.assertRaisesRegex(ValueError, "first key repeats"):
            m.solve([[j], [j]], {j.key}, 1, 1)

    def test_scaling_applies_only_to_read_and_unremovable_maximum(self):
        group = [
            m.Job((0, 0), 90, 80, True),
            m.Job((0, 1), 120, 3, False),
            m.Job((0, 2), 55, 100, True),
        ]
        self.assertEqual(m.wave(group, set(), 4, 5)[0][0], 4 * (5 * 80 + 4 * 90))
        r = m.wave(group, {(0, 0)}, 4, 5)
        self.assertEqual(r[1], (4 * (5 * 100 + 4 * 55), ((0, 0),)))
        r = m.wave(group, {(0, 0), (0, 2)}, 4, 5)
        self.assertEqual(r[2][0], 4 * 5 * 100)
        self.assertEqual(m.wave(group, {(0, 0), (0, 2)}, 1, 1)[2][0], 4 * 100)

    def test_price_on_raw_requires_full_serial_pairs_and_barrier(self):
        records, plan, meta = valid()
        groups, stat = m.extract(records, plan, meta, 0, 10**8)
        self.assertEqual(groups, [[m.Job((0, 2), 30, 15, True)]])
        self.assertEqual(stat["counts"]["published_during_barrier"], 1)
        for mutate in (
            lambda rows: [r for r in rows if r.kind != 16 or r.component != 1],
            lambda rows: [
                r._replace(worker=2) if r.kind == 16 and r.component == 0 else r for r in rows
            ],
            lambda rows: [r._replace(b=16) if r.kind == 16 else r for r in rows],
            lambda rows: [r._replace(ns=r.ns + 4000) if r.kind == 17 else r for r in rows],
        ):
            with self.assertRaises(ValueError):
                m.extract(mutate(records), plan, meta, 0, 10**8)

    def test_repeats_only_pay_set_and_crossing_free(self):
        records, _, meta = valid()
        groups, stat = m.extract(records, [], meta, 0, 10**8)
        self.assertFalse(groups[0][0].first)
        self.assertEqual(m.bounds(groups[0], set(), 1, 1), 60)
        self.assertEqual(stat["counts"]["repeat_reads_granted_free"], 1)
        gs, other = m.extract(records, [], meta, 0, 1_500_000)
        self.assertEqual(gs, [])
        self.assertEqual(other["counts"]["excluded_outside_or_crossing_callback"], 1)


if __name__ == "__main__":
    unittest.main()
