from itertools import combinations, product
from pathlib import Path
from runpy import run_path

S = run_path(Path(__file__).with_name("screen.py"))


def test_interval_optimum_including_crossing_ends():
    intervals = [(0, 3), (0, 1), (1, 2), (0, 2), (2, 3), (0, 4)]
    for mask in product((False, True), repeat=len(intervals)):
        chosen = sorted(
            (p for p, take in zip(intervals, mask, strict=True) if take), key=lambda p: (p[1], p[0])
        )
        for n in (0, 1, 2):
            best = max(
                len(s)
                for k in range(len(chosen) + 1)
                for s in combinations(chosen, k)
                if all(sum(lo <= i < hi for lo, hi in s) <= n for i in range(4))
            )
            assert S["ceiling"](chosen, 0, 0, n) == best


def test_repeated_within_cell_and_arbitrary_warm_entry():
    links, free, first = S["retention_intervals"]([["a", "a", "b"], ["b"], ["a"]])
    assert (free, first) == (1, 2)
    assert S["ceiling"](links, free, first, 0) == 1
    assert S["ceiling"](links, free, first, 1) == 3
