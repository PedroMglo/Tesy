from array import array
from pathlib import Path

import pytest

from tesy.vertical_numerical_diagnostic import (
    RESIDENT,
    ROUTE,
    SLOTS,
    WIDTH,
    f32_add,
    mixed_subset_sum,
    parity,
    read_f32,
    read_slot_mapping,
    sum_slots,
)


def test_f32_sum_respects_stock_and_mixed_association():
    weighted = array("f", [0.0] * (WIDTH * SLOTS))
    for slot, value in enumerate((1e8, 1.0, -1e8, 1.0)):
        weighted[slot * WIDTH] = value
    stock = sum_slots(weighted, (0, 1, 2, 3))
    mixed = mixed_subset_sum(weighted)
    assert ROUTE == (4, 0, 31, 17)
    assert RESIDENT == frozenset((0, 1, 2, 3))
    assert stock[0] == 1.0
    assert mixed[0] == 2.0
    assert f32_add(1e8, 1.0) == 1e8


def test_parity_reports_bitwise_and_finite_numerics():
    reference = array("f", (1.0, 2.0))
    assert parity(reference, array("f", reference))["bitwise"] is True
    changed = parity(reference, array("f", (1.0, 2.25)))
    assert changed["bitwise"] is False
    assert changed["max_abs"] == 0.25


def test_read_f32_rejects_wrong_count_and_nonfinite(tmp_path: Path):
    path = tmp_path / "stage.f32"
    path.write_bytes(array("f", (1.0,)).tobytes())
    with pytest.raises(ValueError, match="expected"):
        read_f32(path, 2)
    path.write_bytes(array("f", (float("nan"),)).tobytes())
    with pytest.raises(ValueError, match="non-finite"):
        read_f32(path, 1)


def test_slot_mapping_fails_closed_on_stale_or_wrong_local_id(tmp_path: Path):
    path = tmp_path / "tool.stderr.txt"
    lines = [
        "vertical diagnostic slot=0 expert=4 backend=CPU local=0 local_id=4 routing_weight=0.1",
        "vertical diagnostic slot=1 expert=0 backend=GPU local=0 local_id=0 routing_weight=0.2",
        "vertical diagnostic slot=2 expert=31 backend=CPU local=1 local_id=31 routing_weight=0.3",
        "vertical diagnostic slot=3 expert=17 backend=CPU local=2 local_id=17 routing_weight=0.4",
    ]
    path.write_text("\n".join(lines) + "\n")
    assert [row["expert"] for row in read_slot_mapping(path)] == list(ROUTE)
    path.write_text("\n".join(line.replace("local_id=0 ", "local_id=1 ") for line in lines))
    with pytest.raises(ValueError, match="global/local"):
        read_slot_mapping(path)
