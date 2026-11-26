from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))


def test_run_needs_both_source_and_destination_and_resets_between_sites():
    run = S["runs"]
    assert run([(1, 3), (2, 4), (3, 8), (5, 9), (6, 10), (7, 11)]) == [2, 1, 3]
    assert run([(7, 11)]) + run([(8, 12)]) == [1, 1]
    assert run([]) == []


def test_key_slot_inheritance_from_nonfirst_victim_and_protection():
    keys, slots = S["KeySlots"](5), S["SlotQueues"](5)

    def demand(layer, ids):
        keys.fills.clear()
        keys.plan(layer, ids)
        fills, _ = slots.plan(layer, ids)
        assert fills == keys.fills and keys.slot == slots.mapping
        return fills

    assert demand(1, [7, 3, 1, 6]) == [(1, 0), (3, 1), (6, 2), (7, 3)]
    assert demand(1, [3, 1, 8, 7]) == [(8, 4)]
    assert demand(1, [3, 1, 9, 7]) == [(9, 2)]
