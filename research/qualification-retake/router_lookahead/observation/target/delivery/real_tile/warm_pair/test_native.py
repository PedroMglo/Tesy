from pathlib import Path
from runpy import run_path

import pytest

MOD = run_path(str(Path(__file__).with_name("build.py")))


def test_warm_program_preserves_frozen_cold_client():
    warm, graph = MOD["specialize"]()
    assert "restore_scoped(*m,plan,occupancy);\n    epochs[0]=now_ns();" in warm
    assert "m->prediction_request(5,1,offers)" in warm
    assert "check_offer_lifecycle(r);" in warm
    assert "warm_selftest();" in warm
    assert "need(active_waves == 3" in graph
    assert "need(active_waves == 4" in (MOD["COLD"] / "graph.inc").read_text()
    assert "queued.size()==125" in (MOD["COLD"] / "native.cpp").read_text()


def test_changed_and_ambiguous_manager_anchors_are_rejected():
    for text in ("missing", "old old"):
        with pytest.raises(Exception, match="changed warm extension anchor"):
            MOD["once"](text, "old", "warm")
