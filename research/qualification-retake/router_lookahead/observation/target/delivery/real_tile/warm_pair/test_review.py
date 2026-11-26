"""Faults for the warm-only attribution and pre-clock restore controls."""

import unittest
from pathlib import Path
from runpy import run_path

R = run_path(str(Path(__file__).with_name("review.py")))
BOUND = {(1, 20, 14, 2)}


def events(seqs):
    log = []
    spans = {}
    tick = 10
    for tid, expert in enumerate(R["OFFERS"], 1):
        log.append([1, expert, tid, -1, 0, tick])
        tick += 1
    for tid, (expert, seq) in enumerate(zip(R["OFFERS"], seqs, strict=True), 1):
        begin = None
        for k in seq:
            s, g = (14, 2) if k in (7, 11) else (-1, 0)
            log.append([k, expert, tid, s, g, tick])
            if k == 2:
                begin = tick * 1000 + 200
            if k == 3:
                spans[expert] = (begin, tick * 1000 + 300)
            tick += 1
    return log, spans


class TicketReview(unittest.TestCase):
    def test_three_distinct_false_lifecycles_and_wait(self):
        log, reads = events([[4], [2, 5, 3, 4], [2, 6, 3, 7, 11, 8], [2, 3, 4]])
        tickets, consumed, stats = R["ticket_report"](log, reads, BOUND, "ON")
        self.assertEqual(consumed, {20})
        self.assertEqual(
            stats,
            dict(
                issued=4,
                consumed=1,
                reads=3,
                waits=1,
                expired_queued=1,
                expired_running=1,
                expired_ready=1,
            ),
        )
        self.assertEqual(tickets[6]["pack_bytes"], 0)
        self.assertEqual(tickets[13]["pack_bytes"], R["WINDOW"])
        self.assertEqual(tickets[20]["wait"]["attach_to_read_done_ns"], [1, 1999])

    def test_queued_demand_falls_back_without_expiry_count(self):
        log, reads = events([[4], [4], [4], [4]])
        tickets, consumed, stats = R["ticket_report"](log, reads, BOUND, "ON")
        self.assertFalse(consumed)
        self.assertEqual(tickets[20]["result"], "queued_demand_fell_back_to_primary")
        self.assertEqual(stats["expired_queued"], 3)
        self.assertEqual(R["ticket_report"]([], {}, BOUND, "OFF")[2]["issued"], 0)

    def test_no_false_confirmation_no_unmatched_read(self):
        log, reads = events([[4], [4], [2, 3, 6, 7, 11, 8], [4]])
        with self.assertRaisesRegex(ValueError, "binding"):
            R["ticket_report"](log, reads, {(1, 20, 14, 1)}, "ON")
        with self.assertRaisesRegex(ValueError, "without stage"):
            R["ticket_report"](log, {**reads, 6: (100, 200)}, BOUND, "ON")
        log, reads = events([[2, 3, 6, 7, 11, 8], [4], [4], [4]])
        with self.assertRaisesRegex(ValueError, "false ticket"):
            R["ticket_report"](log, reads, {(1, 6, 14, 2)}, "ON")


class WarmReview(unittest.TestCase):
    def test_restored_set_occurs_after_pread_and_before_timing(self):
        warm, reads, sets = [], [], []
        for i in range(80):
            layer, slot = divmod(i, 40)
            b = [layer, slot + 7, slot, slot + 1]
            warm.append(dict(zip(("layer", "expert", "slot", "gen"), b, strict=True)))
            t = 10 * i + 1
            reads.append(b + [t, t + 1])
            sets.extend([*b, k, t + 2 + 2 * k, t + 3 + 2 * k] for k in range(3))
        witness = dict(
            records=reads,
            set_intervals=sets,
            worker_acks=4,
            postset_checks=240,
            slab_hashes=240,
            preads=80,
            sets=240,
            elapsed_ns=810,
            pread_bytes=80 * R["WINDOW"],
            set_bytes=240 * R["SLAB"],
            stale_tile_rejected=True,
            initial_policy_verified=True,
            terminal_policy_verified=True,
        )
        prep = {"warm_records": warm}
        self.assertEqual(R["restore"](witness, prep, 820)["set_ns"], 240)
        sets[-1][-1] = 821
        with self.assertRaisesRegex(ValueError, "chronology"):
            R["restore"](witness, prep, 820)


if __name__ == "__main__":
    unittest.main()
