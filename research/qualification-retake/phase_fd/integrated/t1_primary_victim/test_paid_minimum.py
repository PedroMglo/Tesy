import itertools
from pathlib import Path
from runpy import run_path

paid_minimum = run_path(str(Path(__file__).with_name("oracle.py")))["paid_minimum"]


def enumerate_schedules(groups, capacity, start, bank):
    costs = {frozenset(start): 0}
    for group in groups:
        wanted = frozenset(group)
        next_cost = {}
        for old, cost in costs.items():
            extra = old - wanted
            new_cost = cost + len(wanted - old - bank)
            for length in range(min(capacity - len(wanted), len(extra)) + 1):
                for keep in itertools.combinations(extra, length):
                    new = wanted.union(keep)
                    next_cost[new] = min(next_cost.get(new, new_cost), new_cost)
        costs = next_cost
    return min(costs.values())


def test_exhaustive_simultaneous_pins_with_free_reloads():
    groups = [(0,), (1,), (2,), (0, 1), (1, 2), (2, 0)]
    for seq in itertools.product(groups, repeat=3):
        for start in (set(), {0}, {0, 1}):
            for bank in (set(), {1}, {1, 2}):
                assert paid_minimum(seq, 2, start, bank) == enumerate_schedules(seq, 2, start, bank)
