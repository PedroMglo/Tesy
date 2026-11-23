import runpy
from hashlib import sha256
from pathlib import Path

import pytest

audit = runpy.run_path(str(Path(__file__).resolve().parents[1] / "research/post-c320/analyse.py"))


def test_median_discount_keeps_pair_denominators():
    pairs = [
        ({"total_s": 10}, {"total_s": 11, "decode32_s": 5}),
        ({"total_s": 30}, {"total_s": 27, "decode32_s": 15}),
    ]
    assert audit["decode_discount"](pairs, "total_s", 0.10) == pytest.approx(0.20)
    with pytest.raises(ValueError):
        audit["decode_discount"](pairs[:1], "total_s", 0.10)


def test_digest_rejects_same_size_change(tmp_path):
    src = tmp_path / "staging.json"
    receipt = {"sha256": sha256(b"old").hexdigest(), "size_bytes": 3}
    src.write_bytes(b"old")
    assert audit["checked_bytes"](src, receipt) == b"old"
    src.write_bytes(b"new")
    with pytest.raises(ValueError, match="SHA-256"):
        audit["checked_bytes"](src, receipt)


def stage_event(ticket, kind, expert, generation):
    # Timestamps intentionally have a different origin from the primary journal.
    return dict(
        scope=1,
        ticket=ticket,
        kind=kind,
        us=8_000_000,
        call=1,
        layer=2,
        expert=expert,
        slot=expert,
        generation=generation,
    )


def test_two_clocks_overlapping_workers_acceptance_and_ready_hit():
    # Two consumers are waiting during [10,32) and [12,40). A third is a ready hit.
    journal = [
        stage_event(ticket, kind, ticket, 1)
        for ticket, kinds in ((1, (6, 3, 7)), (2, (6, 3, 7)), (3, (3, 6, 7)))
        for kind in kinds
    ]
    stage = {"journal": journal, "stats": {"waits": 2}}
    rows = []

    def add(kind, us, expert=-1, component=-1, route=1):
        rows.append(f"{kind} {us} 1 {route} 2 {expert} {expert} 1 {component} 0 0")

    for expert, enq, deq, copy in ((1, 9, 10, 32), (2, 12, 12, 40), (3, 16, 25, 49)):
        add(4, enq, expert)
        add(5, deq, expert)
        add(8, copy, expert, 0)
    add(4, 13, 4)  # stale work, never accepted
    add(4, 19, 3)  # repeated enqueue of the same accepted generation
    add(11, 20)
    add(12, 38)
    primary = "\n".join([" ".join(audit["FIELDS"]), *rows])
    assert audit["summarize_trace"](primary, stage) == {
        "attached_while_reading": 2,
        "gross_dequeue_to_first_copy_worker_us": 50,
        "gross_dequeue_to_first_copy_wall_us": 30,
        "overlap_with_accepted_queue_and_router_wait_wall_us": 5,
    }
    stage["stats"]["waits"] = 3
    with pytest.raises(ValueError, match="counted waits"):
        audit["summarize_trace"](primary, stage)
    stage["stats"]["waits"] = 2
    journal[2]["generation"] = 2
    with pytest.raises(ValueError, match="generation join"):
        audit["summarize_trace"](primary, stage)


def test_second_call_capacity_bound_uses_strict_threshold():
    rows = []
    # 60 total IDs still permits exactly 40 in call 2. 61 forces overflow.
    for layer in range(36):
        n = {0: 60, 1: 61, 35: 67}.get(layer, 32)
        rows.append(
            {
                "layer": layer,
                "tier": "CPU" if layer < 25 else "CUDA0",
                "demanded_union": list(range(n)),
                "union_count": n,
                "actual_loads": n if layer < 35 else 0,
                "actual_logical_bytes": 32 * n if layer < 35 else 0,
            }
        )
    result = audit["prefill_union_sizes"](rows)
    assert result["CPU"]["above_40"] == 2
    assert result["CPU"]["second_call_min_ids_where_over_40"] == {1: 41}
    assert result["CUDA0"]["second_call_min_ids_where_over_40"] == {35: 47}
    assert result["CPU"]["phase_min_primary_admissions"] == 41
    assert result["CPU"]["second_call_min_primary_admissions"] == 1
    assert result["CUDA0"]["second_call_min_primary_admissions"] == 7
    assert result["CUDA0"]["encoded_expert_payload_bytes"] == 32
    rows[1]["demanded_union"][-1] = 0
    with pytest.raises(ValueError, match="union cardinality"):
        audit["prefill_union_sizes"](rows)
