import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cold_read_fixture_plan", Path(__file__).with_name("plan.py")
)
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)

ROW = plan.analyse.Row(*([0] * len(plan.analyse.Row._fields)))
BEGIN = 1_020_000
END = 2_000_000
META = {(0, r): (16_384 * r + 123, 64) for r in range(3)}


def event(kind, **kw):
    return ROW._replace(kind=kind, **kw)


def job(expert, order=(2, 0, 1), source=0):
    key = {"expert": expert, "gen": 1, "slot": expert}
    queue = [event(k, a=source if k == 12 else 0, **key) for k in (11, 10, 12)]
    read = []
    for i, role in enumerate(order):
        base, size = META[0, role]
        aligned = (base + size * expert) // 4096 * 4096
        begin = BEGIN + 100 * i + 1
        read.append(
            event(
                15,
                begin=begin,
                ns=begin + 20,
                component=role,
                a=aligned,
                b=4096,
                c=4096,
                worker=expert % 4,
                **key,
            )
        )
    return queue, read


def wave(middle):
    return [event(9, ns=BEGIN), *middle, event(23, ns=END)]


def solve(rows, cutoff=4_000_000):
    return plan.assemble(rows, META, 0, cutoff, limit=4 * 16_384)


class PlanTests(unittest.TestCase):
    def test_fifo_not_completion_and_component_order(self):
        qa, ra = job(7)
        qb, rb = job(2)
        groups, floor = solve(wave(qa + qb + rb + ra))
        self.assertEqual(floor, 60)
        jobs = groups[0]["experts"]
        self.assertEqual([j["expert"] for j in jobs], [7, 2])
        self.assertEqual(jobs[0]["components"], [2, 0, 1])
        self.assertEqual(jobs[0]["ranges"][2], [16_384 + 123 + 7 * 64, 64, 16_384, 4096])

    def test_snapshot_preload_cross_wave_and_cut(self):
        qa, ra = job(1)
        qb, rb = job(2, source=1)
        qc, rc = job(3)
        qc[1] = qc[1]._replace(wave=1)
        qd, rd = job(4)
        rows = [event(5, expert=1, a=1), *wave(qa + qb + qc + qd + ra + rb + rc + rd)]
        self.assertEqual([r["expert"] for r in solve(rows)[0][0]["experts"]], [4])
        self.assertEqual(solve(rows, END + 1_000_000)[1], 60)
        self.assertEqual(solve(rows, END + 999_999), ([], 0))

    def test_reject_duplicate_generation_partial_wrong_range_and_clock(self):
        q, r = job(1)
        for changed in (
            [q[0], *q, *r],
            q + r + [r[1]],
            q + r[:-1],
            q + [r[0]._replace(a=r[0].a + 4096), *r[1:]],
            q + [r[0]._replace(c=32), *r[1:]],
            q + [r[0]._replace(worker=3), *r[1:]],
            q + [r[0], r[1]._replace(begin=r[0].ns - 1), r[2]],
            q + [r[0], r[1]._replace(component=r[0].component), r[2]],
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                solve(wave(changed))

    def test_digest_catches_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            path.write_bytes(b'{"n":3}')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(plan.pinned(path, digest), {"n": 3})
            path.write_bytes(b'{"n":4}')
            with self.assertRaisesRegex(ValueError, "changed"):
                plan.pinned(path, digest)


if __name__ == "__main__":
    unittest.main()
