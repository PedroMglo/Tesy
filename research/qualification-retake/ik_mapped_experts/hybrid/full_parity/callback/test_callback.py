import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
RUN = run_path(str(HERE / "run.py"))
G = RUN["OFF"]
T = G["T"]
STUDY = run_path(str(HERE / "study.py"))
S = T["SLAB"]


def fixture():
    # Three bank regions and three independent file intervals for layer zero.
    lines, plan = [], {}
    for k, role in enumerate(T["ROLES"]):
        fo, dst, src = (k + 1) * 128 * S, (k + 1) * 8 * S, (k + 1) * 300 * S
        name = f"blk.0.ffn_{role}_exps.weight"
        plan[name] = fo, 128 * S, 39
        lines.append(f"SET 3 {k} 0 async moe_cache.{name} {dst} 0 {S} {src} {fo}")
        lines.append(f"COPY 3 {k} async 1 {dst} {src} 16 {fo} 0")
        lines.append(f"COPY 3 {k} async 1 {dst + 16} {src + 16} {S - 16} {fo + 16} 0")
    return lines, plan


def test_fragments_and_unobserved_order():
    lines, plan = fixture()
    ledger = [dict(phase="prefill", layer=0, fills=[(0, 0)])]
    c = T["compare"](lines, plan, 2, ledger)
    assert c["match"] and c["missing_slices"] == c["extra_slices"] == 0
    assert c["matrix_requests_B"] == {"prefill": 3 * S, "teacher": 0}
    alternate = T["compare"](lines, plan, 2, [dict(phase="prefill", layer=0, fills=[(0, 1)])])
    assert alternate["missing_slices"] == alternate["extra_slices"] == 3


@pytest.mark.parametrize(
    "fault", ["hole", "duplicate", "early", "role", "source", "write", "overwrite"]
)
def test_transport_refuses_partial_or_ambiguous_data(fault):
    lines, plan = fixture()
    if fault == "hole":
        del lines[2]
    elif fault == "duplicate":
        lines.insert(2, lines[1])
    elif fault == "early":
        lines[0], lines[1] = lines[1], lines[0]
    elif fault == "role":
        lines[0] = lines[0].replace("gate_exps", "up_exps")
    elif fault == "source":
        parts = lines[2].split()
        parts[6] = str(int(parts[6]) + 1)
        lines[2] = " ".join(parts)
    elif fault == "write":
        lines.insert(0, f"COPY 3 999 async 1 {8 * S} 800 16 -1 0")
    elif fault == "overwrite":
        lines.insert(0, f"MEMSET 3 sync {8 * S} 0 4 0")
    with pytest.raises(ValueError):
        T["fills"](lines, plan, 2)


def test_rounding_at_aligned_end_and_overlaps():
    assert STUDY["aligned"](4095, 1, 4096) == 4096
    assert STUDY["aligned"](4095, 2, 4096) == 8192
    assert STUDY["aligned"](4096, 4096, 4096) == 4096
    with pytest.raises(ValueError):
        STUDY["aligned"](0, 0, 4096)


def test_numeric_verdict_requires_both_rows_and_service():
    rows = {str(p): {"bitwise": True} for p in (15, 16)}
    assert G["decision"](rows, True) == "PASS_CALLBACK_OFF_TWO_CUTS"
    assert G["decision"](rows, False) == "INCONCLUSIVE_SERVICE_CONTRAST"
    rows["16"]["bitwise"] = False
    assert G["decision"](rows, False) == "NO_GO_CALLBACK_PARITY"
    with pytest.raises(ValueError):
        G["decision"]({}, True)


@pytest.mark.parametrize(
    "terminal", ["FAIL_PRESERVED", "NO_GO_CALLBACK_PARITY", "INCONCLUSIVE_SERVICE_CONTRAST"]
)
def test_stops_second_arm_on_failure(terminal, tmp_path, monkeypatch):
    globs = RUN["run"].__globals__
    monkeypatch.setitem(globs, "new_authority", lambda a: [{}])

    def attempt(a, folder, mode, authority):
        assert mode == "BANK288"
        row = dict(status=terminal, model_starts=1)
        (folder / "receipt.json").write_text(json.dumps(row))
        return row

    monkeypatch.setitem(globs, "attempt", attempt)
    s = dict(model_starts=0, arms={"BANK161": {"status": "NOT_RUN"}})
    RUN["run"](SimpleNamespace(execute=True, prepared_sha256="sealed"), tmp_path, s)
    assert s["status"] == terminal and s["model_starts"] == 1
    assert s["arms"]["BANK161"]["status"] == "NOT_RUN"
    assert not (tmp_path / "BANK161").exists()
