import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "tesy_continuation_verify", Path(__file__).with_name("verify.py")
)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
MS = 1_000_000


class Sample:
    """Deterministic logical journal. Unit tests never stand in for the native evidence."""

    def __init__(self, mode, schedule):
        self.events = []
        self.raw = dict(mode=mode, schedule=schedule, gates=[], events=self.events, destinations=[])

    def event(self, t, kind, w=-1, e=-1, k=-1, ticket=0, gen=None):
        slot = -1 if gen is None else (4 if e == 1 else 5)
        self.events.append(
            dict(
                seq=0,
                ns=round((1000 + t) * MS),
                tid=301 + w,
                worker=w,
                kind=kind,
                expert=e,
                component=k,
                slot=slot,
                generation=gen or 0,
                ticket=ticket,
            )
        )

    def tick(self, t, kind, e, k=-1):
        self.event(t, kind, e - 1, e, k, 10 + e)

    def order(self):
        self.events.sort(key=lambda r: r["ns"])
        for i, row in enumerate(self.events, 1):
            row["seq"] = i
        return self.raw


def timeline(mode, schedule):
    t = Sample(mode, schedule)
    emit = t.event
    for w in range(4):
        emit(-30 + w, "worker_enter", w)
    emit(0, "t0")
    release = {1: 450, 2: 250, 3: 350 if schedule == "early" else 1400}
    direct_worker = 1 if mode == "A" else 3
    direct_accept = 260 if mode == "A" else 3
    accept1 = 2
    publish1 = 456
    read4 = direct_accept + 1
    finish4 = read4 + 655
    for e, opened in release.items():
        t.tick(-15 + e, "stage_start", e)
        begin = -10 + e
        t.tick(begin, "stage_read_begin", e, 0)
        t.raw["gates"].append(
            dict(
                expert=e,
                arrival_ns=(1000 + begin) * MS + 1,
                deadline_ns=(1000 + opened) * MS,
                opened_ns=(1000 + opened) * MS + 1,
            )
        )
        t.tick(opened + 0.1, "stage_read_end", e, 0)
        for k in (1, 2):
            t.tick(opened + 0.3 * k, "stage_read_begin", e, k)
            t.tick(opened + 0.3 * k + 0.1, "stage_read_end", e, k)
        t.tick(opened + 1, "stage_complete", e)
    emit(0.5, "barrier_begin")
    emit(accept1, "primary_accept", 3, 1, gen=1)
    if mode == "A":
        emit(2.5, "park", 3, 1, ticket=11, gen=1)
        emit(452, "resume", 3, 1, ticket=11, gen=1)
        publisher = 3
    else:
        emit(2.5, "defer", 3, 1, ticket=11, gen=1)
        emit(452, "handoff", 0, 1, ticket=11, gen=1)
        publisher = 0
    emit(453, "claim", publisher, 1, ticket=11, gen=1)
    for k in range(3):
        emit(454 + k * 0.5, "copy_begin", publisher, 1, k, gen=1)
        emit(454 + k * 0.5 + 0.1, "copy_end", publisher, 1, k, gen=1)
    emit(publish1, "primary_publish", publisher, 1, gen=1)
    emit(direct_accept, "primary_accept", direct_worker, 4, gen=1)
    t.raw["gates"].append(
        dict(
            expert=4,
            arrival_ns=(1000 + read4) * MS + 1,
            deadline_ns=(1650 + read4) * MS + 1,
            opened_ns=(1650 + read4) * MS + 10,
        )
    )
    for k in range(3):
        when = read4 + 650 + k
        emit(read4 if not k else when, "direct_read_begin", direct_worker, 4, k, gen=1)
        emit(when + 0.1, "direct_read_end", direct_worker, 4, k, gen=1)
        emit(when + 0.2, "copy_begin", direct_worker, 4, k, gen=1)
        emit(when + 0.3, "copy_end", direct_worker, 4, k, gen=1)
    emit(finish4, "primary_publish", direct_worker, 4, gen=1)
    for dt, kind in enumerate(("barrier_end", "remap_return", "finish_entry", "finish_begin"), 1):
        emit(finish4 + dt, kind)
    drained = max(finish4 + 5, release[3] + 2)
    for dt, kind in enumerate(("finish_end", "finish_return", "shutdown")):
        emit(drained + dt, kind)
    for w in range(4):
        emit(drained + 3 + w, "worker_exit", w)
    t.raw.update(
        counters=v.control.COUNTERS | {"waits": int(mode == "A")},
        terminal=v.control.TERMINAL | {"pending_continuations": 0},
        issued_components=[[0] * 3] + [[1] * 3 for _ in range(4)],
        delivered_components=[[0] * 3] + [[1] * 3 for _ in range(4)],
    )
    return t.order()


def fault(stale):
    t = Sample("B", "stale" if stale else "fault")
    for w in range(4):
        t.event(-10 + w, "worker_enter", w)
    t.tick(0, "stage_start", 1)
    t.tick(1, "stage_read_begin", 1, 0)
    t.event(3, "primary_accept", 1, 1, gen=1)
    t.event(4, "defer", 1, 1, ticket=11, gen=1)
    if stale:
        t.event(5, "new_generation", -1, 1, gen=2)
        t.tick(6, "stage_read_end", 1, 0)
        for k in (1, 2):
            t.tick(6 + k, "stage_read_begin", 1, k)
            t.tick(6 + k + 0.1, "stage_read_end", 1, k)
    else:
        t.tick(6, "stage_read_error", 1, 0)
    t.tick(10, "stage_complete", 1)
    t.event(11, "continuation_reject", 0, 1, ticket=11, gen=1)
    for dt, kind in enumerate(("finish_entry", "finish_begin", "finish_throw", "shutdown")):
        t.event(13 + dt, kind)
    for w in range(4):
        t.event(20 + w, "worker_exit", w)
    expected = [[0] * 3 for _ in range(5)]
    delivered = copy.deepcopy(expected)
    expected[1] = [1, 1, 1] if stale else [1, 0, 0]
    if stale:
        delivered[1] = [1] * 3
    t.raw.update(
        counters=dict(
            issued=1,
            reads=1,
            completed_reads=int(stale),
            expired_running=0,
            waits=0,
            consumed=0,
            errors=int(not stale),
            peak_running_spec=1,
        ),
        terminal=v.control.TERMINAL
        | dict(pending_continuations=0, load_failed=True, claimed=int(stale)),
        issued_components=expected,
        delivered_components=delivered,
        gates=[dict(expert=1, arrival_ns=1002 * MS, deadline_ns=0, opened_ns=1005 * MS + 1)],
        fault=dict(
            slot=4,
            original_generation=1,
            observed_generation=2 if stale else 1,
            observed_expert=1,
            claimed=int(stale),
            state="LOADING",
            finish_threw=True,
            message="CPU staging byte service failed",
            injected_errno=0 if stale else 5,
            restart_rejected=True,
        ),
    )
    return t.order()


def arm(r):
    # The shared byte verifier has its own full-size positive/corruption fixtures.
    with patch.object(
        v.control, "verify_destinations", return_value=[{"sha256": "fixture-only"}]
    ) as check:
        result = v.verify_arm(r, r["mode"], r["schedule"], Path("."))
        check.assert_called_once_with(r["destinations"], Path("."))
        return result


class Verify(unittest.TestCase):
    def test_full_order_and_pair_signs(self):
        arms = [arm(timeline(m, s)) for s in ("early", "late") for m in "ABBA"]
        r = v.compare_family(arms)
        self.assertEqual(r["timing"], "PASS")
        self.assertEqual([p["finish_advantage_ns"] for p in r["pairs"]], [257 * MS] * 2 + [0] * 2)
        self.assertTrue(arms[4]["producer_3_done_after_finish_entry"])
        self.assertFalse(arms[0]["producer_3_done_after_finish_entry"])
        arms[0]["logical_read_bytes"] -= 1
        with self.assertRaisesRegex(ValueError, "unequal work"):
            v.compare_family(arms)

    def test_strict_threshold_and_outlier(self):
        arms = [arm(timeline(m, s)) for s in ("early", "late") for m in "ABBA"]
        arms[0]["remap_ns"] = arms[1]["remap_ns"] + 100 * MS
        self.assertEqual(v.compare_family(arms)["timing"], "INCONCLUSIVE")
        arms[0]["remap_ns"] += 1
        arms[4]["finish_ns"] = arms[5]["finish_ns"] - 100 * MS
        self.assertEqual(v.compare_family(arms)["timing"], "INCONCLUSIVE")
        arms[4]["finish_ns"] += 1
        self.assertEqual(v.compare_family(arms)["timing"], "PASS")
        arms[4]["timing_eligible"] = False
        self.assertEqual(v.compare_family(arms)["mechanism"], "PASS")
        self.assertEqual(v.compare_family(arms)["timing"], "INCONCLUSIVE")

    def test_gate_deadline_is_anchored_to_direct_arrival(self):
        r = timeline("B", "early")
        r["gates"][-1]["deadline_ns"] += 100
        with self.assertRaisesRegex(ValueError, "deadline"):
            arm(r)

    def test_late_gate_is_ineligible_without_changing_mechanism(self):
        r = timeline("B", "early")
        gate = r["gates"][-1]
        late = 151 * MS
        gate["opened_ns"] += late
        for event in r["events"]:
            if event["ns"] >= gate["deadline_ns"] and event["kind"] != "worker_enter":
                event["ns"] += late
        self.assertFalse(arm(r)["timing_eligible"])

    def test_precedence_and_identities(self):
        for key, replace, reason in [
            ("defer", {"ticket": 15}, "ticket"),
            ("handoff", {"worker": 2, "tid": 303}, "worker"),
            ("primary_accept", {"generation": 2}, "generation"),
        ]:
            r = timeline("B", "early")
            row = next(x for x in r["events"] if x["kind"] == key)
            row.update(replace)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, reason):
                arm(r)

    def test_fault_native_gates(self):
        for stale in (True, False):
            r = fault(stale)
            self.assertTrue(v.verify_fault(r, r["schedule"])["load_failed"])
            r["fault"]["claimed"] = 1 - int(stale)
            with self.assertRaisesRegex(ValueError, "claimed"):
                v.verify_fault(r, r["schedule"])

    def test_reject_incomplete_work_and_stale_publication(self):
        r = timeline("A", "late")
        r["delivered_components"][3][2] = 0
        with self.assertRaisesRegex(ValueError, "transfer counts"):
            arm(r)
        r = fault(True)
        row = next(x for x in r["events"] if x["kind"] == "continuation_reject")
        row.update(kind="primary_publish", ticket=0)
        with self.assertRaisesRegex(ValueError, "missing"):
            v.verify_fault(r, "stale")

    def test_event_elision_and_duplicate_accept(self):
        r = timeline("B", "early")
        original = next(
            x for x in r["events"] if x["kind"] == "primary_accept" and x["expert"] == 1
        )
        duplicate = next(x for x in r["events"] if x["kind"] == "claim")
        duplicate.update(original, ns=duplicate["ns"], seq=duplicate["seq"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            arm(r)


if __name__ == "__main__":
    unittest.main()
