from pathlib import Path
from runpy import run_path

import pytest

S = run_path(str(Path(__file__).with_name("prepare.py")))


def test_eviction_recovers_original_slot():
    m, rev = {}, {}
    S["install"](m, rev, 0, [(1, 4), (2, 7)])
    S["install"](m, rev, 1, [(3, 4)])
    assert m == {(0, 2): 7, (1, 3): 4} and rev[4] == (1, 3)
    with pytest.raises(ValueError, match="duplicate"):
        S["install"](m, rev, 0, [(9, 4), (10, 4)])


def test_distinct_selected_map_preserves_order_and_rejects_alias_and_false_hit():
    ids = [8, 3, 27, 11]
    before = [-1] * 128
    before[8], before[27] = 80, 11
    after = before.copy()
    after[3], after[11] = 10, 256
    fills = [(3, 10), (11, 256)]
    r = S["group"](0, ids, before, after, fills, [4096, 8192, 12288])
    assert r["selected_compact_slots"] == [2, 0, 1, 3]
    assert [row[:2] for row in r["weight_sets_role_expert_ik_slot_compact_slot_src_mod_page"]] == [
        [role, e] for role in ("gate", "up", "down") for e in (3, 11)
    ]
    r = S["group"](0, ids, after, after, [], [4096, 8192, 12288])
    assert r["hits_to_seed_before_clock"] == ids
    with pytest.raises(ValueError, match="misses"):
        S["group"](0, ids, before, after, [], [4096, 8192, 12288])
    after[27] = after[8]
    with pytest.raises(ValueError):
        S["group"](0, ids, after, after, [], [4096, 8192, 12288])
