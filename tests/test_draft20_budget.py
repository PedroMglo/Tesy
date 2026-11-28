from pathlib import Path
from runpy import run_path

import pytest

UNIT = Path(__file__).resolve().parents[1] / "research/ready-experts/draft20"
REVIEW = run_path(UNIT / "review.py")
FRONT = run_path(UNIT / "frontier.py")


def test_reference_reconstructs_rollback_bonus_and_tail():
    case = dict(
        serial_matches=[False, True, False, True, True, False, False, False],
        serial_ns=[5] * 8,
        blocks=[[1, 0, 3, 4, 2, 0], [2, 1, 2, 5, 0, 0], [4, 2, 4, 2, 0, 1]],
        tail_ns=[9, 9],
    )
    rows = REVIEW["replay"](case)
    w = {"ticks_ns": list(range(0, 90, 10))}
    inside = REVIEW["price"](rows, w, 5, 60, 60)
    assert inside["straddles"] and inside["blocks"] == 3
    assert inside["prior_alignment_and_undo_ns"] == 2
    assert inside["last_alignment_and_undo_granted_ns"] == 1
    assert inside["serial_tail_ns"] == 0 and inside["paid_draft_target_ns_per_block"] == 9
    full = REVIEW["price"](rows, w, 8, 80, 80)
    assert full["serial_tail_ns"] == 20
    case["blocks"][0][-2] = 0
    with pytest.raises(ValueError, match="KV conservation"):
        REVIEW["replay"](case)


@pytest.mark.parametrize("price", [0, 17, 45])
def test_atomic_cut_frontier_agrees_with_exhaustive_schedules(price):
    clock = [0, 19, 90, 110, 125, 148, 155, 170]
    matched = [True, True, False, False, True, True, False]
    case = {"serial_matches": matched, "serial_ns": [9] * 7}
    w = dict(ticks_ns=clock, first_final_ns=1010, cut=2, decode_ns=173)
    pairs = []

    def all_paths(pos, total, first):
        if first is None and pos >= 2:
            first = total
        if pos == 7:
            pairs.append((first, total))
            return
        all_paths(pos + 1, total + clock[pos + 1] - clock[pos], first)
        if 7 - pos >= 3:
            depth = 0 if not matched[pos] else 1 + int(matched[pos + 1])
            all_paths(pos + depth + 1, total + price + 9 + (9 if depth else 0), first)

    all_paths(0, 0, None)
    options = FRONT["path_options"](case, w, "paid", price)
    obtained = [(r["first_ns"] - 920, r["decode_ns"] - 3) for r in options]
    assert all(pair in pairs for pair in obtained)
    assert all(any(f <= x and e <= z for f, e in obtained) for x, z in pairs)
