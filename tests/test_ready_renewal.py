from itertools import product
from pathlib import Path
from runpy import run_path

import pytest

R = run_path(Path(__file__).resolve().parents[1] / "research/ready-experts/renewal/replay.py")


def job(layer, expert, read, copy, required=True):
    key = (layer, expert)
    return R["Transfer"](key, R["Job"](key, read, copy), required, False, False)


def test_exclusive_promotes_before_demoting_without_overfilling():
    a, b, c = [(0, i) for i in range(3)]
    bank = R["Bank"](1, [b], {a})
    assert bank.reserve(b, a) == (True, None)
    assert set(bank.lru) == {a} and bank.primary == {b}
    assert bank.reserve(c, b) == (False, a)
    assert bank.peak == 1 and set(bank.lru) == {b} and bank.primary == {c}
    with pytest.raises(ValueError):
        bank.reserve(c, b)


def test_initial_ownership_and_optional_acquisitions():
    available = {(0, 0)}
    records = [
        job(0, 0, 6, 5),
        job(0, 1, 3, 8),
        job(0, 1, 11, 2),
        job(0, 2, 1, 9, False),
        job(0, 2, 7, 1),
    ]
    assert R["first_acquisitions"](records, available) == [R["Job"]((0, 1), 3, 2)]
    assert available == {(0, 0), (0, 1), (0, 2)}
    assert R["first_acquisitions"]([job(0, 1, 17, 3), job(1, 1, 7, 4)], available) == [
        R["Job"]((1, 1), 7, 4)
    ]


def test_unlimited_first_touch_cost_cannot_exceed_either_real_generation():
    for first_required, second_required in product((True, False), repeat=2):
        a = job(0, 7, 10, 2, first_required)
        b = job(0, 7, 7, 12, second_required)
        forced = R["first_acquisitions"]([a, b], set())
        cost = sum(j.read_ns + j.set_ns for j in forced)
        assert cost <= min(r.price.read_ns + r.price.set_ns if r.mandatory else 0 for r in (a, b))
