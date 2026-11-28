from itertools import pairwise, permutations
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest

reach = run_path(Path(__file__).with_name("reach.py"))


def test_output_mask_and_shared_boundaries():
    tiers = {i: "CPU" if i < 25 else "CUDA0" for i in range(36)}
    call = dict(number=1, geometry=[(5, 2044, 2048)], enter_ns=0, return_ns=80)
    waves = [SimpleNamespace(site=(1, 1, i, 0), start=2 * i + 1, end=2 * i + 2) for i in range(35)]
    counts, ns = reach["eligibility"](call, tiers, waves)
    assert counts["cpu_prefill"] == 25 and ns["cpu_prefill"] == ns["cpu_both"] == 51
    assert ns["cpu_decode"] == 0
    with pytest.raises(ValueError, match="layer or tile ordering"):
        reach["eligibility"](call, tiers, waves[1:])


def test_union_never_double_spends_or_reorders_clocks():
    assert reach["union_ns"]([(9, 11), (0, 7), (8, 10), (4, 7)]) == 10
    with pytest.raises(ValueError, match="reversed interval"):
        reach["union_ns"]([(3, 2)])


def test_layout_bound_dominates_all_permutations():
    batches = [[0, 1, 3], [0, 2], [1, 2, 2], [0, 3], [3, 4, 1], [], [2]]
    result = run_path(Path(__file__).with_name("batch.py"))["certificate"](batches, 5)

    def saved(layout):
        return sum(a in b and z in b for a, z in pairwise(layout) for b in batches)

    assert saved(range(5)) == result["numeric_adjacent"]
    best = max(saved(layout) for layout in permutations(range(5)))
    assert best + result["repeated"] <= result["command_saving_upper"] < result["generations"]
