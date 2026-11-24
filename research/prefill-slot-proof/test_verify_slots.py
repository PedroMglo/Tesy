"""Small symbolic fixture for the copy/checkout proof (no model or C135 data)."""

import unittest

from verify_slots import EXPERT_BYTES, PART_BYTES, verify


def fixture():
    rows = []
    call, width = 1, 5

    def emit(kind, layer=-1, expert=-1, slot=-1, **fields):
        row = dict(kind=kind, seq=len(rows), layer=layer, expert=expert, slot=slot,
                   victim=-1, wave=-1, n_tokens=width, state=-1, generation=0,
                   logical_bytes=0, component=-1, call_id=call)
        row.update(fields)
        rows.append(row)
        return row["seq"]

    def replace(old, new, slot):
        emit("DEMAND", 0, new, -1, state=0)
        eviction = emit("EVICT", 0, old, slot, state=2, victim=new)
        emit("RESERVE", 0, new, slot)
        for kind in ("ENQUEUE", "DEQUEUE", "LOAD_BEGIN"):
            emit(kind, 0, new, slot, generation=8,
                 logical_bytes=EXPERT_BYTES if kind == "LOAD_BEGIN" else 0)
        for component in range(3):
            for kind in ("READ_BEGIN", "READ_END", "TENSOR_SET_BEGIN", "TENSOR_SET_RETURN"):
                emit(kind, 0, new, slot, generation=8, component=component,
                     logical_bytes=PART_BYTES)
        emit("LOAD_END", 0, new, slot, generation=8, logical_bytes=EXPERT_BYTES)
        return eviction

    emit("CALL_BEGIN")
    emit("DEMAND", 0, 27, 3, state=2)
    emit("CALL_END")
    call, width = 2, 148
    emit("CALL_BEGIN")
    width = 32
    emit("DEMAND", 0, 13, 6, state=2)  # X in the previous tile.
    emit("DEMAND", 1, 1, 1, state=2)
    source = replace(13, 15, 6)         # Copy X into the idle slot of 27.
    emit("DEMAND", 1, 1, 1, state=2)
    target = replace(27, 13, 3)         # Serve X from the earlier copy.
    emit("DEMAND", 1, 1, 1, state=2)
    emit("DEMAND", 0, 13, 3, state=2)
    emit("DEMAND", 1, 1, 1, state=2)
    width = 20
    emit("DEMAND", 0, 15, 6, state=2)
    emit("CALL_END", n_tokens=148)
    call, width = 3, 1
    emit("CALL_BEGIN")
    emit("DEMAND", 0, 13, 3, state=2)
    emit("CALL_END")
    return rows, [(source, target)]


class CertificateTests(unittest.TestCase):
    def test_copy_and_control_rejoin_before_first_decode(self):
        rows, schedule = fixture()
        report = verify(rows, schedule)
        self.assertEqual(report["loads_avoided"], {"CPU": 1})
        self.assertEqual(report["same_tier_copy_payload_bytes"], EXPERT_BYTES)
        self.assertEqual(report["load_generations"], [[0, 3, 8]])
        self.assertEqual(report["equal_payload_at_call_ends"], [2, 3])
        self.assertEqual(report["first_decode_demands"], 1)
        self.assertEqual(verify(rows, [])["verified_pairs"], 0)

    def test_unproven_destination(self):
        rows, schedule = fixture()
        rows[1].update(slot=-1, state=0)
        with self.assertRaisesRegex(ValueError, "proven idle READY"):
            verify(rows, schedule)

    def test_displaced_consumer_anywhere_in_source_tile(self):
        rows, schedule = fixture()
        source, _ = schedule[0]
        rows[source - 1].update(expert=27, slot=3, state=2)
        with self.assertRaisesRegex(ValueError, "consumed or parked"):
            verify(rows, schedule)

    def test_intermediate_overwrite(self):
        rows, schedule = fixture()
        source, _ = schedule[0]
        rows[source + 2].update(kind="EVICT", layer=0, slot=3, expert=27, state=2, victim=1)
        with self.assertRaisesRegex(ValueError, "intermediate eviction"):
            verify(rows, schedule)

    def test_conflicting_endpoints(self):
        rows, schedule = fixture()
        with self.assertRaisesRegex(ValueError, "reused endpoint"):
            verify(rows, schedule * 2)

    def test_same_physical_slot(self):
        rows, schedule = fixture()
        a, b = schedule[0]
        rows[b]["slot"] = rows[a]["slot"]
        with self.assertRaisesRegex(ValueError, "incompatible substitution"):
            verify(rows, schedule)

    def test_prior_consumer_missing(self):
        rows, schedule = fixture()
        rows[4].update(expert=2, slot=22)
        with self.assertRaisesRegex(ValueError, "earlier tile consumer"):
            verify(rows, schedule)

    def test_corrupt_component_and_stale_generation(self):
        for overwrite, message in (({"component": 1}, "component identity"),
                                   ({"generation": 9}, "worker identity"),
                                   ({"logical_bytes": 17}, "component identity")):
            with self.subTest(overwrite=overwrite):
                rows, schedule = fixture()
                _, target = schedule[0]
                rows[target + 5].update(overwrite)
                with self.assertRaisesRegex(ValueError, message):
                    verify(rows, schedule)

    def test_target_wrong_decode_payload(self):
        rows, schedule = fixture()
        rows[-2]["expert"] = 27
        with self.assertRaisesRegex(ValueError, "demand payload mismatch"):
            verify(rows, schedule)


if __name__ == "__main__":
    unittest.main()
