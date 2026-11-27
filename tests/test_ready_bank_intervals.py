from collections import Counter
from itertools import combinations, product
from pathlib import Path
from runpy import run_path

import pytest

INTERVALS = run_path(
    Path(__file__).resolve().parents[1] / "research/ready-experts/renewal/intervals.py"
)
COMPOSE = run_path(
    Path(__file__).resolve().parents[1] / "research/ready-experts/renewal/composition.py"
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


def test_swap_cost_matches_reference_and_preserves_region_boundaries():
    reg, job = COMPOSE["RE"]["Region"], COMPOSE["RE"]["Job"]
    groups = [
        reg((1, 0, 0), 9, [job(1, 20, 5), job(2, 40, 2)]),
        reg((1, 0, 1), 12, [job(3, 31, 1)]),
    ]
    edges = [4, 7, 6]
    data = {"P106": ([(1, groups, edges)], {"first_final": 10, "decode": 1})}
    prices = COMPOSE["Prices"](data["P106"][0], {1})
    ref = COMPOSE["INTERVAL"]["C"]["cuts"]
    for n in range(4):
        for toggled in combinations((1, 2, 3), n):
            hits = {1} ^ set(toggled)
            service = [
                COMPOSE["B"]["layer_fourths"](
                    [j.set_ns + (0 if j.expert in hits else j.read_ns) for j in g.jobs]
                )
                for g in groups
            ]
            wall, _ = ref([4 * g.internal for g in groups], [4 * e for e in edges], service)
            assert prices.base[1] + prices.delta(set(toggled)) == (wall + 3) // 4
    adjusted, _ = COMPOSE["discount"](data, {"P106": {groups[0].site: {"inside": 3, "edge": 5}}})[
        "P106"
    ]
    assert adjusted[0][1][0].internal == 6 and adjusted[0][2] == [4, 2, 6]
    assert groups[0].internal == 9 and edges == [4, 7, 6]
    with pytest.raises(ValueError):
        COMPOSE["discount"](data, {"P106": {groups[0].site: {"edge": 8}}})


def test_later_wave_deadline_tracks_generation_and_paid_publication():
    deadlines = run_path(Path(INTERVALS["HERE"]) / "deadlines.py")
    wave = deadlines["SRC"]["Wave"]
    a, b, c, d = [(0, 1, gen, 42) for gen in range(4)]
    waves = [
        wave((1, 0, 0, 0), 1, True, 4, False, {a, b, c, d}, {a}),
        wave((1, 0, 0, 1), 5, False, 7, True, set(), {b}),
        wave((1, 1, 0, 0), 9, True, 12, True, set(), {c}),
    ]
    stamps = {a: (1, 4), b: (2, 6), c: (2, 8), d: (3, 10)}
    assert deadlines["consumers"](waves, stamps) == {
        a: "same_wave",
        b: "later_wave_same_tile_layer",
        c: "later_region",
        d: "no_consumer",
    }
    with pytest.raises(ValueError):
        deadlines["consumers"](waves, {**stamps, b: (2, 8)})
