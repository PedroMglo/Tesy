from __future__ import annotations

import argparse

import tesy.cli as cli


def test_plan_cli_fails_closed_when_inconclusive(monkeypatch):
    monkeypatch.setattr(cli, "load_lock", lambda: {"models": [{"id": "m"}]})
    monkeypatch.setattr(cli, "get_model", lambda lock, model_id: {"id": model_id})
    monkeypatch.setattr(cli, "collect_snapshot", lambda path: {})
    monkeypatch.setattr(
        cli,
        "plan_capacity",
        lambda model, snapshot, artifact_bytes: {"status": "INCONCLUSIVE"},
    )

    args = argparse.Namespace(command="plan", model="m", path=None)
    assert cli._run(args) == 2
