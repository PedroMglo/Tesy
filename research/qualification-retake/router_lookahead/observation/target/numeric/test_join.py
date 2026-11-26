from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest

M = run_path(Path(__file__).with_name("join.py"))


def event(kind, **values):
    defaults = dict(kind=kind, layer=35, begin=0, ns=100, component=-1, a=0, b=0, c=0)
    return SimpleNamespace(**(defaults | values))


def source():
    width, n = 2880, 29
    result = [
        event(35, a=34, b=3, c=n, begin=50),
        event(32, a=34, b=n * 4 * width, c=M["COEFFICIENTS"], ns=101),
    ]
    for j, size in enumerate((n * width * 4, width * 4, width * 4, width * 128 * 4, 512)):
        result.append(event(36, component=j, a=size, b=3, c=0, begin=102 + 2 * j, ns=103 + 2 * j))
    result.append(event(33, a=0x04030201, b=28, c=188, ns=115))
    return result


def test_final_layer_reads_full_input_and_projects_selected_final_row():
    assert M["source_site"](source(), [(28, 188)]) == {188: (115, (1, 2, 3, 4))}


@pytest.mark.parametrize(
    "i,field,value",
    [(3, "component", 0), (4, "c", 1), (5, "begin", 80), (6, "a", 5120), (7, "b", 0)],
)
def test_rejects_role_buffer_order_extent_and_row(i, field, value):
    rows = source()
    setattr(rows[i], field, value)
    with pytest.raises(ValueError):
        M["source_site"](rows, [(28, 188)])


def test_checked_occupancy_including_claimed_generation():
    record = event(34, a=1, b=1, slot=4, gen=3, expert=7)
    owners = {(35, 7): (35, 4)}
    state = {(35, 4): (3, 7, 1)}
    M["lookup"](record, owners, state, {(35, 4, 3, 7)})
    with pytest.raises(ValueError):
        M["lookup"](record, owners, state, set())
    record.gen = 2
    with pytest.raises(ValueError):
        M["lookup"](record, owners, state, {(35, 4, 2, 7)})
