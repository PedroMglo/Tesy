from pathlib import Path
from runpy import run_path

import pytest

R = run_path(Path(__file__).resolve().parents[1] / "research/ready-experts/primary/replay.py")


def job(site, e, s, gen, due):
    return R["Load"](site, (site[2], s, gen, e), 0, 0, due)


def test_first_acquisition_comes_from_routes_and_is_independent_of_slot():
    a = (1, 0, 0, 0)
    b = (1, 0, 0, 1)
    c = (2, 0, 0, -1)
    groups = [
        {"site": a, "ranks": [3, 4, 4, 5]},
        {"site": b, "ranks": []},
        {"site": c, "ranks": [3, 6, 5, 4]},
    ]
    cold = R["cold_sites"](groups, {(0, 3), (0, 4)})
    assert cold == {(0, 5): a[:3], (0, 6): c[:3]}
    assert R["first_acquisitions"]([job(a, 5, 1, 7, b), job(c, 6, 3, 10, c)], cold) == {
        (0, 5): 1,
        (0, 6): 2,
    }
    with pytest.raises(ValueError):
        R["first_acquisitions"]([job(c, 5, 1, 1, c), job(c, 6, 0, 4, c)], cold)


def test_read_and_copy_matching_have_distinct_conditions():
    a = (1, 0, 0, 0)
    b = (1, 0, 0, 1)
    old = job(a, 8, 1, 7, b)
    moved = job(a, 8, 3, 9, b)
    shifted = job(b, 7, 2, 3, b)
    ref = {old.match: old}
    for strict in (False, True):
        regs, unknown_reads, unknown_sets = R["priced"](
            [moved, shifted], ref, {old.key: (9, 4)}, exact_slot=strict
        )
        assert [(j.read_ns, j.set_ns) for j in regs[a[:3]]] == [(9, 0 if strict else 4), (0, 0)]
        assert unknown_reads == {2} and unknown_sets == ({1, 2} if strict else {2})
