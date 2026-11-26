import struct
from pathlib import Path
from runpy import run_path

import pytest

S = run_path(str(Path(__file__).with_name("score.py")))


def test_root_ties_are_not_unique_in_either_direction():
    routes = {(0, 0): (2, 1, 3, 4), (0, 1): (0, 1, 2, 3)}
    other = {(0, 0): (1, 2, 3, 4), (0, 1): (0, 1, 2, 4)}
    tie = [2, 2] + [0] * 30
    unique = [2, 1] + [0] * 30
    for a, b in ((tie, unique), (unique, tie), (tie, tie)):
        r = S["compare"](
            {"routes": routes, "logits": {0: a, 32: unique}},
            {"routes": other, "logits": {0: b, 32: unique}},
        )
        assert r["strict_greedy_positions"]["prefill"] == {
            "same": [],
            "changed": [],
            "either_tied": [0],
        }
        assert r["strict_greedy_positions"]["teacher"]["same"] == [32]
        assert r["top_two_on_changed_tied_and_teacher"][32][0]["margin"] == 1
        assert r["route_groups"]["prefill:L0"]["positions"]["same_set_reordered"] == [0]
        assert r["route_groups"]["prefill:L1"]["positions"]["set_changed"] == [0]


def test_nonfinite_and_truncated_rows_rejected():
    for data in (bytes(124), struct.pack("<32f", float("nan"), *([0] * 31))):
        with pytest.raises(ValueError):
            S["logit_rows"](data, 1)


def test_logical_route_excludes_distinct_copy():
    line = "ROUTE 4 ffn_moe_topk-0 1,2,3,4"
    alias = "ROUTE 4 ffn_moe_topk-0 (cont) 1,2,3,4"
    rows, copies = S["route_rows"](line + "\n" + alias)
    assert rows == {(32, 0): (1, 2, 3, 4)} and copies == 1
    for bad in (alias, line + "\n" + line, line + "8", line[:-2], line + "\n" + alias[:-1] + "5"):
        with pytest.raises(ValueError):
            S["route_rows"](bad)
