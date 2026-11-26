"""The historical physical supervisor checks its per-arm plan digest after the child exits."""

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace


def test_branch_passes_frozen_plan_before_start(tmp_path, monkeypatch):
    run = run_path(str(Path(__file__).with_name("run.py")))["run"]
    module = run.__globals__
    plan = "frozen test plan digest"
    state = {"profile": {"plan_sha256": plan}}
    bindings = tuple(range(6)) + ({}, {}, set(), set())
    args = SimpleNamespace(prepared=tmp_path, prepared_sha256="test", unit="tesy-ik-e10-input-test")
    monkeypatch.setitem(module, "freeze", lambda _: (state, bindings, (), ()))
    monkeypatch.setitem(
        module, "receipt", lambda *args: dict(status="PREPARED_ONLY", authority=state)
    )
    observed = []

    def before_launch(mode, a, folder, arm, bound):
        observed.append((mode, arm["plan_sha256"], arm["model_starts"]))
        raise ValueError("injected before launch")

    monkeypatch.setitem(
        module,
        "FR",
        {
            "OPS": {"arm": before_launch},
            "save": lambda *args: None,
            "available_rows": lambda *_: {},
        },
    )
    monkeypatch.setitem(module, "REAL", {"close_arm": lambda *args: None})
    monkeypatch.setitem(module, "sha", lambda *_: "test receipt")
    result = {"model_starts": 0, "arms": {}}
    run(args, tmp_path, result)
    assert observed == [("BANK288", plan, 0)]
    assert (result["stop_arm"], result["model_starts"]) == ("ORIGINAL_OFF", 0)
    assert result["reason"] == "ValueError: injected before launch"
