"""Invented integer clocks test accounting only; the fixture never opens a pack."""

import copy
import unittest

from review import ORDER, SLAB, WINDOW, review_arm


def fixture(layout="STAGED", mode="DETAIL"):
    sets = 0 if layout == "DIRECT" else 3
    r = dict(
        schema="tesy-c291-five-misses-v1",
        status="PASS_C291_FIVE_MISS_SERVICE",
        clock="MONOTONIC_RAW_NS",
        layout=layout,
        observer=mode,
        ready_workers=4,
        joined_workers=4,
        workers_before_destructor=4,
        load_count=5,
        requested_bytes=5 * WINDOW,
        logical_bytes=15 * SLAB,
        set_count=5 * sets,
        verified_payload=True,
        queue_empty=True,
        confirmed_slots=[[e, i, 1] for i, e in enumerate(ORDER)],
        outer_start=90,
        t0=100,
        last_publication=140,
        resume=143,
        outer_end=147,
        prefault_faults=dict(
            scope="RUSAGE_SELF",
            minflt_before=70,
            minflt_after=195,
            minflt_delta=125,
            majflt_before=1,
            majflt_after=1,
            majflt_delta=0,
        ),
        events=[],
    )
    if mode == "MIN":
        return r
    for i, e in enumerate(ORDER):
        w = i % 4
        t = 100 if i < 4 else 121
        p = 119 if i < 4 else 140

        def event(kind, time, component, count, worker=w, expert=e, slot=i):
            r["events"].append(
                dict(
                    event=kind,
                    ns=time,
                    worker=(-1 if kind == "enqueue" else worker),
                    expert=expert,
                    slot=slot,
                    generation=1,
                    component=component,
                    bytes=count,
                )
            )

        event("enqueue", 92 + i, -1, 0)
        event("read_begin", t, -1, WINDOW)
        event("read_end", t + 10, -1, WINDOW)
        for k in range(sets):
            event("set_begin", t + 10 + 2 * k, k, SLAB)
            event("set_end", t + 12 + 2 * k, k, SLAB)
        event("publish", p, -1, 0)
    return r


class TestReview(unittest.TestCase):
    def test_overlap_is_counted_only_once(self):
        v = review_arm(fixture())
        self.assertEqual(v["publication_ns"], 40)
        self.assertEqual(v["read_worker_ns"], 50)
        self.assertEqual(v["read_union_ns"], 20)
        self.assertEqual(v["set_worker_ns"], 30)
        self.assertEqual(v["set_union_ns"], 12)
        self.assertEqual(v["read_or_set_union_ns"], 32)
        self.assertEqual(v["last_experts"], [49])

    def test_direct_and_minimal_have_no_fabricated_sets(self):
        self.assertEqual(review_arm(fixture("DIRECT"))["set_worker_ns"], 0)
        self.assertNotIn("read_worker_ns", review_arm(fixture("DENSE", "MIN")))

    def test_mutations(self):
        r = fixture()
        q = fixture()
        q["events"].pop()
        faults = [q]
        for key, value in [
            ("set_count", 0),
            ("last_publication", 142),
            ("ready_workers", 3),
            ("logical_bytes", 5 * WINDOW),
            ("observer", "MIN"),
        ]:
            q = copy.deepcopy(r)
            q[key] = value
            faults.append(q)
        for index, key, value in [
            (0, "expert", 60),
            (1, "worker", 3),
            (3, "component", 2),
            (5, "generation", 0),
            (-1, "ns", 139),
            (-9, "ns", 115),
        ]:
            q = copy.deepcopy(r)
            q["events"][index][key] = value
            faults.append(q)
        for i, f in enumerate(faults):
            with self.subTest(i=i), self.assertRaises(ValueError):
                review_arm(f)

    def test_prefault_accounting_required_in_both_modes(self):
        for mode in ("MIN", "DETAIL"):
            r = fixture(mode=mode)
            del r["prefault_faults"]
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "prefault scope"):
                review_arm(r)
            for field, value in (
                ("scope", "RUSAGE_THREAD"),
                ("minflt_before", -1),
                ("majflt_before", 2),
                ("majflt_delta", False),
                ("minflt_delta", 124),
                ("minflt_after", None),
            ):
                r = fixture(mode=mode)
                r["prefault_faults"][field] = value
                with self.subTest(mode=mode, field=field), self.assertRaisesRegex(
                    ValueError, "prefault"
                ):
                    review_arm(r)


if __name__ == "__main__":
    unittest.main()
