import hashlib
import importlib.util
import itertools
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pfj1_t1_victim_audit", Path(__file__).with_name("audit.py")
)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def row(kind, **fields):
    values = {key: 0 for key in subject.fd.Row._fields}
    values.update(kind=kind, ns=1, tile=-1, wave=-1, layer=-1, slot=-1, expert=-1, worker=-1)
    values.update(fields)
    return subject.fd.Row(**values)


def slots():
    return [
        row(5, call=1, layer=layer, slot=slot, gen=0, a=0)
        for layer in range(36)
        for slot in range(40)
    ]


class T1Evictions(unittest.TestCase):
    def test_unknown_start_bounds_and_washout(self):
        a, b, c, d = (0, 0), (25, 1), (1, 1), (29, 2)
        victims = [a, a, b, c, a, d, b, c, d, c]
        result = subject.lru(victims, 3)
        self.assertEqual(result["ordered_keys"], [list(b), list(d), list(c)])
        self.assertTrue(result["identified"])
        per_tier = {"cpu": [], "cuda": []}
        for k in range(4):
            for perm in itertools.permutations((a, b, c, d), k):
                initial = list(perm)
                copies = {tier: 0 for tier in per_tier}
                for key in victims:
                    if key not in initial:
                        copies[subject.key_tier(key)] += 1
                        initial = initial[-2:]
                    else:
                        initial.remove(key)
                    initial.append(key)
                self.assertEqual(initial, [b, d, c])
                for tier in per_tier:
                    per_tier[tier].append(copies[tier])
        for tier, counts in per_tier.items():
            self.assertEqual(min(counts), result["minimum_copies_over_unknown_start_by_tier"][tier])
            self.assertEqual(max(counts), result["cold_start_copies_by_tier"][tier])
        self.assertFalse(subject.lru([a, b, b], 3)["identified"])

    def test_ready_gated_generation_and_queue(self):
        s = slots()
        s[0] = row(5, call=1, layer=0, slot=0, expert=10, gen=2, a=2)
        first = row(11, call=1, layer=0, slot=0, expert=11, gen=3, a=10)
        queue = first._replace(kind=12, a=0)
        service = first._replace(kind=13)
        publish = first._replace(kind=17)
        again = first._replace(expert=12, gen=4, a=11)
        result, fifo, evictions = subject.state_before(s + [first, queue, service, publish, again])
        self.assertEqual(result[0], (12, 4, 1, 0))
        self.assertEqual((fifo, evictions), ([], [(0, 10), (0, 11)]))
        with self.assertRaisesRegex(ValueError, "READY publication"):
            subject.state_before(s + [first, queue, publish])
        with self.assertRaisesRegex(ValueError, "victim generation"):
            subject.state_before(s + [first, queue, service, again])
        queue_after_claim = subject.state_before(s + [first, queue, service])[0][0]
        self.assertEqual(queue_after_claim, (11, 3, 1, 1))

    def test_contiguous_trajectory_before_second_post(self):
        enter = row(1, call=1, a=1, b=2118, c=2118)
        returns = row(2, call=1)
        t1 = [
            enter,
            *slots(),
            returns,
            enter._replace(call=2, b=2119, c=2119),
            returns._replace(call=2),
        ]
        self.assertEqual(subject.capture_prefix(t1)["last_position"], 2119)
        for broken in (
            t1[:-1],
            [enter._replace(b=2117, c=2117), *t1[1:]],
            [enter._replace(a=5), *t1[1:]],
        ):
            with self.assertRaises(ValueError):
                subject.capture_prefix(broken)

    def test_projection_protects_rank_bindings_not_worker_clock(self):
        ranks = row(27, call=1, layer=0, tile=1, a=0x1020304)
        reserve = row(11, call=1, layer=0, tile=1, slot=1, gen=2, expert=1, a=0)
        dispatch = reserve._replace(kind=13, worker=1)
        publish = dispatch._replace(kind=17)
        second = reserve._replace(expert=2, slot=2)
        old = [ranks, reserve, dispatch, publish, second]
        new = [
            r._replace(call=3, ns=728, worker=3)
            for r in [ranks, reserve, dispatch, second, publish]
        ]
        baseline = subject.authority_projection(old, 1)
        result = subject.compare_projections(subject.authority_projection(new, 3), baseline)
        self.assertTrue(result["host"]["equal"])
        self.assertFalse(result["service"]["equal"])
        for i, change in ((0, dict(a=0x1020403)), (1, dict(slot=2)), (2, dict(gen=1))):
            mutation = list(new)
            mutation[i] = mutation[i]._replace(**change)
            with self.assertRaisesRegex(ValueError, "route/order/binding"):
                subject.compare_projections(subject.authority_projection(mutation, 3), baseline)

    def test_record_seal_excludes_mutable_header(self):
        original = [row(1, call=1, a=1, b=2119, c=2119), row(2, call=1)]
        raw = b"".join(subject.fd.RECORD.pack(*r) for r in original)
        self.assertEqual(subject.record_digest(original), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(
            subject.record_digest(original), subject.record_digest(original, sealed=True)
        )
        with self.assertRaisesRegex(ValueError, "pre-POST digest"):
            subject.audit(
                [*original, row(1, a=5)],
                {},
                [],
                None,
                {"records": 2, "bytes": len(raw), "sha256": subject.record_digest(original[::-1])},
            )


if __name__ == "__main__":
    unittest.main()
