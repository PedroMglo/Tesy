import itertools
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

F = run_path(str(Path(__file__).with_name("oracle.py")))


def test_certificate_dominates_exhaustive_optimum_and_coincident_hits_only_count_once():
    a, b, c = (0, 1), (0, 2), (2, 3)
    features = {frozenset((a, b)): [7] * 4, frozenset((a, c)): [5] * 4, frozenset((c,)): [6] * 4}
    assert F["gains"](features, {a, b}) == [12] * 4
    for cap in (1, 2):
        optimum = max(
            F["gains"](features, set(keys))[0] for keys in itertools.combinations((a, b, c), cap)
        )
        order = F["greedy"](features, (1, 0, 0, 0), cap)
        assert F["gains"](features, set(order))[0] <= optimum
        assert all(
            F["upper_bound"](features, set(order[:i]), cap, 0) >= optimum for i in range(cap + 1)
        )


def test_unavailable_origin_and_free_prefix_cannot_gain_time_twice():
    def wave(layer, reserved, start_drained, end_drained):
        return SimpleNamespace(
            site=(3, 0, layer, 0),
            start=0,
            end=10,
            reserved=reserved,
            start_drained=start_drained,
            end_drained=end_drained,
        )

    a = (1, 0, 1, 7)
    b = (12, 0, 1, 8)
    seq = [
        wave(1, {a}, True, False),
        wave(12, {b}, False, False),
        wave(25, set(), False, True),
        wave(26, {b}, True, True),
    ]
    features = {}
    F["coverage"](seq, ["prefill", "prefill", "anchor"], {(1, 7)}, True, 0, features)
    assert F["gains"](features, {(1, 7), (12, 8)}) == [10, 10, 0, 0]
    assert F["gains"](features, {(12, 8)}) == [0] * 4
