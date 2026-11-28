from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

T = run_path(Path(__file__).resolve().parents[1] / "research/ready-experts/primary/two_turns.py")


def test_penultimate_reference_counts_independent_routed_visits():
    h = T["History"]()
    h.visit(0, [1, 1, 1, 3])
    h.visit(0, [1, 3])
    h.visit(0, [2, 2, 2, 2])
    pool = SimpleNamespace(ids=[1, 2, 3])
    assert h.previous[0][2] == 0
    assert h.choose(0, 1, pool, {2}, set()) == 0
    assert h.choose(0, 2, pool, {2}, set()) == 1
    assert h.choose(0, 2, pool, {2}, {1, 3}) == 0
    assert h.epoch[1] == 0


def test_private_victim_rule_preserves_pins_native_function_and_full_slot_trajectory():
    h = T["History"]()
    initial = [(s, 1, 2, 0) for _ in range(36) for s in range(40)]
    orig = T["R"]["Manager"].callback.__globals__["victim"]
    for k in (1, 2):
        mgr = T["with_policy"](initial, h, k, [set() for _ in range(36)])
        ids = [0, 1, 2, 40]
        h.visit(0, ids)
        alloc, demanded = mgr.callback(0, -1, ids)
        assert alloc == [(40, 3, 2, 3, 0)]
        assert [e for e, _, _ in demanded] == ids
        assert T["snapshot"](mgr)[3] == (40, 2, 2, 0)
    assert T["R"]["Manager"].callback.__globals__["victim"] is orig


def test_captures_only_new_ready_payloads_in_first_turn():
    bank = T["FirstTurn"]()
    bank.reserve(1, 0, 1, -1)
    bank.reserve(1, 0, 2, 1)
    bank.reserve(10, 0, 3, 1)
    assert list(bank.held) == [(0, 1)]
    assert bank.traffic["prefill", "CPU"]["captured_payloads"] == 1
    assert bank.traffic["decode", "CPU"]["captured_payloads"] == 0
    assert sum(bank.training.values()) == 3
