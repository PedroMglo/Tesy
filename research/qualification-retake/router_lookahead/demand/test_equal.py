from pathlib import Path
from runpy import run_path

compare = run_path(Path(__file__).with_name("equal.py"))["compare"]


def test_identical_issue_budget_including_zero():
    assert compare([3, 5, 7], [5], {5, 7})["recency_wins"] == 1
    r = compare([], [4], {4})
    assert r["each_issues"] == r["projection_hits"] == r["recency_hits"] == 0
    assert r["zero_issues"] == r["ties"] == 1
