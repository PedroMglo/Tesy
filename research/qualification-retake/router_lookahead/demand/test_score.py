from pathlib import Path
from runpy import run_path

M = run_path(Path(__file__).with_name("score.py"))


def test_limit_applies_after_resident_filter_with_stable_tie():
    rows = [[4, 2, 3, 1], [4, 2, 6, 5]]
    assert M["choose"](rows, {4, 127}, 4) == ([2, 1, 3, 5], 1)
    assert M["choose"](rows, {4, 127}, None) == ([2, 1, 3, 5, 6], 1)


def test_one_offer_covers_one_generation_only():
    counts = M["classify"]([4, 6, 7], {4, 6}, {4: [(0, 100), (1, 200)]}, 0)
    assert counts["jobs_hit"] == counts["hit_first_wave"] == 1
    assert counts["eligible_jobs"] == 2 and counts["hit_later_wave"] == 0
    assert counts["offered_routed_without_job"] == counts["offered_unused"] == 1
