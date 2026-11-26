from pathlib import Path
from runpy import run_path

import pytest

R = run_path(str(Path(__file__).with_name("review.py")))


def test_overlap_does_not_add_simultaneous_worker_time():
    calc = R["overlap"]([(2, 7), (3, 5), (9, 11)], (1, 10), [(1, 4), (6, 8)], [(3, 7)], [(4, 9)])
    assert calc["spec_read_summed_worker_ns"] == 9
    assert calc["spec_read_wall_union_ns"] == 7
    assert calc["spec_read_in_graph0_wall_ns"] == 6
    assert calc["spec_read_in_graph0_summed_worker_ns"] == 8
    assert calc["spec_read_in_graph0_remap_wall_ns"] == 3
    assert calc["spec_read_in_graph0_outside_remaps_wall_ns"] == 3
    assert calc["spec_read_in_graph0_with_either_primary_service_wall_ns"] == 4


def test_pair_contract_and_worker_edges():
    assert R["outcome"]([14, 10, 12, 17]) == ([4, 5], "GO_NEXT_PAIR_FIXTURE")
    assert R["outcome"]([9, 10, 12, 12]) == ([-1, 0], "INCONCLUSIVE_TRAVERSAL_TIMING")
    assert R["peak"]([(1, 3), (2, 3), (3, 5), (4, 4)]) == 2
    with pytest.raises(ValueError):
        R["merged"]([(3, 1)])


def test_ticket_inflight_vs_ready():
    row = {
        "mode": "ON",
        "stage": {"issued": 4, "reads": 1, "consumed": 1, "waits": 1},
        "stage_events": [],
    }
    for i, e in enumerate(R["OFFERS"], 1):
        kinds = [1, 2, 6, 3, 7, 11, 8] if i == 1 else [1, 4]
        for u, k in enumerate(kinds, 1):
            row["stage_events"].append([k, e, i, 2, 1, u])
    assert R["tickets"](row, [42], {(1, 42, 2, 1)}) == {42}
    with pytest.raises(ValueError):
        R["tickets"](row, [42], {(1, 42, 2, 2)})
    row["stage"]["waits"] = 0
    with pytest.raises(ValueError):
        R["tickets"](row, [42], {(1, 42, 2, 1)})


def test_microsecond_stage_quantization_does_not_grant_exact_completion():
    events = [(2, 42, 1, -1, 0, 6), (3, 42, 1, -1, 0, 9)]
    r = R["stage_residency"](events, (5000, 9500))
    assert (r["stage_in_graph0_wall_lower_ns"], r["stage_in_graph0_wall_upper_ns"]) == (2001, 3500)
    assert (r["completed_by_graph0_end_certain"], r["completed_by_graph0_end_possible"]) == (0, 1)


def test_pending_promotion_preserves_fifo_and_claim_under_either_completion_order():
    key = (1, 42, 3, 2)
    other = (0, 11, 7, 1)

    def ev(k, b, d):
        return [k, *b, d]

    events = [
        ev(4, key, 2),
        ev(4, other, 0),
        ev(4, key, 1),
        ev(5, key, -1),
        ev(5, other, -1),
        ev(64, key, 8),
        ev(10, other, -1),
        ev(10, key, -1),
    ]
    raw = {
        "queue_events": events,
        "queue_enqueues": 3,
        "queue_skips": 1,
        "preloads": 1,
        "promoted_bindings": [key],
    }
    report = R["queue"](raw, {key, other})
    assert report["by_layer"]["1"] == {
        "first_demand": 0,
        "first_preload": 1,
        "promotions": 1,
        "skips": 1,
        "enqueues": 2,
        "pops": 2,
        "unique_claims": 1,
        "publications": 1,
    }
    assert report["skip_reason_masks"] == {8: 1}
    # The other worker can complete the first claim before polling its duplicate.
    finished = events[:5] + [events[7], ev(64, key, 2), events[6]]
    assert R["queue"](dict(raw, queue_events=finished), {key, other})["skip_reason_masks"] == {2: 1}
    broken = events[:]
    broken[3], broken[4] = broken[4], broken[3]
    with pytest.raises(ValueError):
        R["queue"](dict(raw, queue_events=broken), {key, other})
    broken = events[:]
    broken[5] = ev(5, key, -1)
    with pytest.raises(ValueError):
        R["queue"](dict(raw, queue_events=broken), {key, other})
    duplicate = events[:2] + [ev(4, other, 0)] + events[2:]
    with pytest.raises(ValueError):
        R["queue"](dict(raw, queue_events=duplicate), {key, other})
