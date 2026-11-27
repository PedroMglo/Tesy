from collections import Counter
from itertools import combinations, product
from pathlib import Path
from runpy import run_path

import pytest

INTERVALS = run_path(
    Path(__file__).resolve().parents[1] / "research/ready-experts/renewal/intervals.py"
)


def test_equal_price_selection_maximizes_cardinality_with_half_open_boundaries():
    ends = range(1, 5)
    for origins in product(*(range(e) for e in ends)):
        starts = dict(zip(ends, origins, strict=True))
        for capacity in (1, 2):

            def fits(subset, starts=starts, capacity=capacity):
                return all(sum(starts[e] <= t < e for e in subset) <= capacity for t in range(4))

            best = max(n for n in range(5) for subset in combinations(ends, n) if fits(subset))
            chosen = INTERVALS["maximum_count"](starts, capacity)
            assert len(chosen) == best and fits(chosen)
            for selected in (
                chosen,
                INTERVALS["expensive_first"](starts, {e: e for e in ends}, capacity),
            ):
                _, peak = INTERVALS["assign"](starts, selected, capacity)
                assert fits(selected) and peak <= capacity


def test_accept_only_matching_victim_and_generation_before_slot_reuse():
    a, b, c = ((0, i) for i in range(3))
    tx = [
        INTERVALS["Reservation"](k, v, (i,), "prefill")
        for i, (k, v) in enumerate([(a, b), (b, c), (c, a)])
    ]
    starts = INTERVALS["opportunities"](tx, [a])
    assert starts == {1: 0, 2: 1, 3: 2}
    slots, peak = INTERVALS["assign"](starts, starts, 1)
    assert peak == 1
    assert INTERVALS["audit"](tx, [a], starts, slots, 1)["CPU"] == {"captures": 2, "promotions": 3}
    with pytest.raises(ValueError):
        INTERVALS["audit"](tx, [a], {**starts, 3: 1}, slots, 1)
    with pytest.raises(ValueError):
        INTERVALS["assign"]({1: 0, 2: 0}, {1, 2}, 1)


def test_causal_frequency_may_decline_a_victim_and_pays_unused_captures():
    a, b, c, d = ((0, i) for i in range(4))
    tx = [INTERVALS["Reservation"](k, v, (), "decode") for k, v in [(b, c), (a, d)]]
    recent, recent_bytes, _ = INTERVALS["online"](tx, [a], None, 1)
    frequent, frequency_bytes, peak = INTERVALS["online"](tx, [a], Counter({a: 10}), 1)
    assert not recent and recent_bytes["CPU"]["captures"] == 2
    assert frequent == {2} and peak == 1
    assert frequency_bytes["CPU"] == {"captures": 1, "promotions": 1}
