"""Independent event fixtures. No model, file descriptor or workers are used here."""

import os
import unittest
from pathlib import Path
from runpy import run_path

A = run_path(str(Path(__file__).with_name("audit.py")))
Row = A["PFJ"]["Row"]


def row(kind, tick, **fields):
    baseline = dict.fromkeys(Row._fields, -1)
    baseline.update(
        ns=tick,
        begin=0,
        gen=0,
        a=0,
        b=0,
        c=0,
        kind=kind,
        call=1,
        tile=1,
        layer=1,
        error=0,
        reserved=0,
    )
    baseline.update(fields)
    return Row(**baseline)


def pack(*ids):
    return int.from_bytes(bytes(ids), "little")


def site(late=False):
    # Both token rows use the same four experts. The toy predictions match three.
    events = []

    def append(kind, **fields):
        t = len(events) + 3
        events.append((t, row(kind, t, **fields)))

    append(32, a=0, b=48, c=144)

    def predict():
        for i in range(2):
            append(33, a=pack(1, 0, 2, 5), b=i, c=2044 + i)

    if not late:
        predict()
    append(9, a=2, b=4)
    for i in range(2):
        append(27, a=pack(0, 2, 1, 3), b=i)
    for e in range(4):
        state = (0, 1, 2, 2)[e]
        append(34, expert=e, slot=e if state else -1, gen=int(bool(state)), a=state)
    for e in range(4):
        append(10, expert=e, slot=e, gen=1)
    append(19, a=1)
    append(20, a=1)
    append(23)
    if late:
        predict()
    tile_rows = [(i, row(31, i + 1, a=i, b=2044 + i)) for i in range(2)]
    return events, tile_rows


def service():
    # A complete cold catalogue and one real-geometry, synthetic resident transition.
    rows = []

    def add(kind, **fields):
        rows.append(row(kind, 2 * len(rows) + 2, **fields))

    add(7, fd=7, b=7, c=os.O_DIRECT)
    for layer in range(36):
        for slot in range(40):
            add(5, layer=layer, slot=slot, expert=-1)
        for role in range(3):
            add(8, layer=layer, component=role, fd=7, a=(layer * 3 + role) * 16384, b=128)
    job = dict(slot=2, expert=1, gen=1)
    add(34, expert=1, slot=-1)
    add(11, a=-1, **job)
    add(12, **job)
    add(10, **job)
    add(19, a=1)
    add(13, worker=2, **job)
    for role in range(3):
        args = dict(worker=2, component=role, fd=7, **job)
        add(15, a=(3 + role) * 16384, b=4096, c=4096, begin=2 * len(rows) + 1, **args)
        add(16, a=128, b=256, begin=2 * len(rows) + 1, **args)
    add(17, worker=2, **job)
    add(20, a=1)
    add(34, tile=2, a=2, **job)
    for worker in range(4):
        add(24, worker=worker)
    return rows


class AuditTests(unittest.TestCase):
    def test_same_row_hits_do_not_multiply_service(self):
        summary, credit, native = A["join_site"](*site())
        self.assertEqual(summary["matched_rank_offers"], 6)
        self.assertEqual(
            summary["early_matched_keys_by_lookup_state"], dict(absent=1, ready=1, loading=1)
        )
        self.assertEqual(credit, {(1, 0, 1, 0)})
        self.assertEqual(len(native), 2)

    def test_start_without_available_is_late(self):
        summary, credit, _ = A["join_site"](*site(late=True))
        self.assertEqual(summary["available_after_remap_rows"], 2)
        self.assertEqual(summary["before_lookup_distinct_matched_keys"], 0)
        self.assertFalse(credit)

    def test_cross_position_or_void_component_rejected(self):
        events, tile_rows = site()
        i = next(i for i, (_, e) in enumerate(events) if e.kind == 33)
        idx, e = events[i]
        events[i] = idx, e._replace(c=e.c + 1)
        with self.assertRaisesRegex(ValueError, "position"):
            A["join_site"](events, tile_rows)
        rows = service()
        jobs, _, times = A["check_service"](rows)
        self.assertEqual(len(jobs), 1)
        self.assertEqual([len(times[i]) for i in (15, 16)], [3, 3])
        i = next(i for i, e in enumerate(rows) if e.kind == 16 and e.component == 1)
        with self.assertRaisesRegex(ValueError, "ordered READ/SET"):
            A["check_service"](rows[:i] + rows[i + 1 :])

    def test_mutated_generation_state_or_claim_rejected(self):
        rows = service()
        i = next(i for i, e in enumerate(rows) if e.kind == 34 and e.tile == 2)
        for change in [dict(gen=2), dict(a=1), dict(b=1)]:
            mutated = list(rows)
            mutated[i] = rows[i]._replace(**change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "lookup"):
                A["check_service"](mutated)


if __name__ == "__main__":
    unittest.main()
