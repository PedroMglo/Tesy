from itertools import combinations, product
from pathlib import Path
from runpy import run_path

import pytest

optimal = run_path(str(Path(__file__).with_name("score.py")))["optimal"]


def brute(groups, slots):
    universe = {key for group in groups for key in group}

    def states(keys):
        return [
            frozenset(s) for n in range(min(slots, len(keys)) + 1) for s in combinations(keys, n)
        ]

    choices = dict.fromkeys(states(universe), 0)
    for g in map(set, groups):
        downstream = {}
        for held, cost in choices.items():
            for new in states(held | g):
                misses = cost + len(g - held)
                downstream[new] = min(misses, downstream.get(new, misses))
        choices = downstream
    return min(choices.values())


def test_exhaustive_group_order_capacity_and_bypass():
    groups = [(), (0,), (1,), (2,), (0, 1), (1, 2), (0, 1, 2)]
    for stream in product(groups, repeat=3):
        for capacity in range(4):
            assert optimal(stream, capacity) == brute(stream, capacity)
    for copies in (2, 3):
        steps = [(1,), (0, 2), (1,), (2,)]
        fragments = [tuple((k, i) for k in g for i in range(copies)) for g in steps]
        assert optimal(steps, 1) * copies == brute(fragments, copies)


def test_streamed_read_can_bypass_a_full_cache():
    assert optimal([(0,), (1,), (0,), (1,), (0,)], 1) == 2
    with pytest.raises(ValueError, match="duplicate"):
        optimal([(0, 0)], 1)
