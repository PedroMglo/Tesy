from fractions import Fraction
from pathlib import Path
from runpy import run_path

import pytest

STUDY = Path(__file__).resolve().parents[1] / "research/ready-experts/cpu_wave"
REVIEW = run_path(STUDY / "review.py")
CLIENT = REVIEW["CLIENT"]


def arms():
    rows = []
    for role in CLIENT["ORDER"]:
        value = 9.0 if role == "ON" else 10.0
        t1 = dict(valid_s=10.0)
        t2 = dict(first_final_s=value, valid_s=value + 1, prefill_s=4.0, decode_s=5.0)
        rows.append(dict(role=role, turns=[t1, t2]))
    return rows


def test_both_mirrored_contrasts_and_exact_protection_boundary():
    rows = arms()
    rows[3]["turns"][0]["valid_s"] = 10.5
    rows[2]["turns"][1]["decode_s"] = 5.25
    pairs, result = CLIENT["compare"](rows)
    assert result == "GO_COMPONENT_NOMINAL"
    assert [p["control"] for p in pairs] == ["ORIGINAL", "OFF", "ORIGINAL", "OFF"]
    rows[2]["turns"][1]["decode_s"] = 5.250001
    assert CLIENT["compare"](rows)[1] == "INCONCLUSIVE_NOMINAL"


def test_opposite_sign_in_valid_completion_does_not_pass_on_first_content():
    rows = arms()
    rows[3]["turns"][1]["valid_s"] = 11.1
    assert CLIENT["compare"](rows)[1] == "INCONCLUSIVE_NOMINAL"


def test_all_ties_close_this_application():
    rows = arms()
    for r in rows:
        r["turns"][1]["first_final_s"] = 12.0
        r["turns"][1]["valid_s"] = 13.0
    assert CLIENT["compare"](rows)[1] == "NO_GO_COMPONENT_NOMINAL"


def test_role_order_is_required():
    with pytest.raises((ValueError, RuntimeError), match="mirrored order"):
        CLIENT["compare"](arms()[:3])


def test_published_decision_reproduces_without_weights_or_device():
    REVIEW["verify"](REVIEW["read"](STUDY / "decision.json"))


def test_total_threshold_and_strict_sign_of_each_pair():
    threshold = run_path(STUDY / "composition.py")["threshold"]

    def row(total):
        return dict(total_s=Fraction(total), prefill153_s=Fraction(10))

    assert threshold(list(map(row, [20, 20, 20, 20])))[0] == 160_000
    assert threshold(list(map(row, [20, 25, 12, 20])))[0] == 500_001


def test_supplied_work_budgets_from_the_public_arms():
    composition = run_path(STUDY / "composition.py")
    report = composition["run"](None)
    original = REVIEW["read"](STUDY / "composition.json")
    assert report["arms"] == original["arms"]
    for case, computed in report["cases"].items():
        for field, value in computed.items():
            assert value == original["cases"][case][field]
