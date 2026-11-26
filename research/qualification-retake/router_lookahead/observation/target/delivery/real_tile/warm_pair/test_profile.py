"""Fault-inject paid warm-up, unused offers and official SET work without a model."""

from pathlib import Path
from runpy import run_path

import pytest

P = run_path(str(Path(__file__).with_name("profile.py")))


def sample():
    jobs = [(0, i) for i in range(28)] + [(1, i) for i in (20, 22, 23, 24)]
    binds = [[layer, expert, i % 40, 2] for i, (layer, expert) in enumerate(jobs)]
    warm = [[layer, slot + 50, slot, 1, 1, 2] for layer in (0, 1) for slot in range(40)]
    restore = dict(
        preads=80,
        pread_bytes=80 * P["WINDOW"],
        sets=240,
        set_bytes=240 * P["SLAB"],
        slab_hashes=240,
        postset_checks=240,
        worker_acks=4,
        elapsed_ns=10,
        initial_policy_verified=True,
        terminal_policy_verified=True,
        records=warm,
        set_intervals=[[*r[:4], k, 2, 3] for r in warm for k in (0, 1, 2)],
    )
    return dict(
        status="PASS_WARM_TILE",
        grade="EXACT",
        mode="ON",
        offers=P["OFFERS"],
        workers=4,
        drained=True,
        restore=restore,
        slot_bindings=binds,
        reads=[[*j, int(j == (1, 20)), 4, 5] for j in jobs] + [[1, 6, 1, 4, 5]],
        read_jobs=33,
        pread_bytes=33 * P["WINDOW"],
        slab_hashes=99,
        stage={"reads": 2, "consumed": 1},
        sets=96,
        service=[[*b, k, 6, 7] for b in binds for k in (0, 1, 2)],
        epochs_ns=list(range(1, 9)),
        elapsed_ns=7,
        drain_ns=2,
        numeric={"L0": 1, "L1": 2},
    )


def test_paid_unused_read_is_legal():
    row = sample()
    assert P["check_row"](row, "EXACT", "ON") == (row["numeric"], row["slot_bindings"])


def test_unused_read_cannot_publish():
    row = sample()
    row["service"][-1][1] = 6
    with pytest.raises(ValueError, match="SET"):
        P["check_row"](row, "EXACT", "ON")


@pytest.mark.parametrize(
    "field,value",
    [
        ("worker_acks", 3),
        ("postset_checks", 239),
        ("pread_bytes", 0),
        ("terminal_policy_verified", False),
    ],
)
def test_restore_is_a_gate_in_its_own_right(field, value):
    row = sample()
    row["restore"][field] = value
    with pytest.raises(ValueError, match="restore"):
        P["check_row"](row, "EXACT", "ON")


def test_double_consumption_of_the_only_useful_offer_fails():
    row = sample()
    row["stage"]["consumed"] = 2
    with pytest.raises(ValueError, match="consumption"):
        P["check_row"](row, "EXACT", "ON")
