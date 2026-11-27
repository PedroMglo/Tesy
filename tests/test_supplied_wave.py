from pathlib import Path
from runpy import run_path

import pytest

STUDY = Path(__file__).resolve().parents[1] / "research/ready-experts/cpu_wave/supplied"
REVIEW = run_path(STUDY / "review.py")
BOUND = run_path(STUDY / "executor_bound.py")


def family(first, second):
    arms = []
    for i, role in enumerate("RGPWWPGR"):
        pre, dec = {3: first, 4: second}.get(i, (50.0, 50.0))
        arms.append(
            dict(
                role=role,
                name=str(i + 1) + role,
                metrics=dict(prefix_s=100.0, prefill153_s=pre, decode32_s=dec, total_s=pre + dec),
            )
        )
    return dict(arms=arms)


def test_independent_controls_need_both_positive_signs_and_the_other_case():
    pair = {"nominal153": family((46, 46), (46, 46)), "code153": family((52.5, 52.5), (52.5, 52.5))}
    assert REVIEW["compare"](pair, "G", "W")["global_cases"] == ["nominal153"]
    pair["code153"] = family((52.501, 52.5), (52.501, 52.5))
    assert not REVIEW["compare"](pair, "G", "W")["global_cases"]
    pair["code153"] = family((50, 50), (50, 50))
    pair["nominal153"] = family((50, 50), (25, 45))
    assert not REVIEW["compare"](pair, "R", "W")["global_cases"]


def test_phase_only_and_decode_paths_are_distinct():
    pair = {"code153": family((50, 50), (50, 50)), "nominal153": family((45, 51), (45, 51))}
    result = REVIEW["compare"](pair, "P", "W")
    assert result["global_cases"] == []
    assert result["phase_survivors"] == [dict(case="nominal153", phase="prefill153_s")]
    assert result["positive_prefill_component_cases"] == ["nominal153"]
    pair["nominal153"] = family((54, 42), (54, 42))
    assert REVIEW["compare"](pair, "R", "W")["global_cases"] == ["nominal153"]


def test_one_prefix_and_two_decode_intervals_do_not_double_credit_the_tail():
    limit = BOUND["LIMITS"]
    observed = dict(first_final=limit["first_final"] + 6, decode=limit["decode"] + 3)
    phase = dict(prefill=4, decode_before_final=3, decode_tail=1)
    exterior = dict(first_final=6, decode=3)
    report = BOUND["price"](observed, phase, exterior)
    assert report["full_client"]["first_final"]["removable_ns"] == 7
    assert report["full_client"]["decode"]["removable_ns"] == 4
    assert report["full_client"]["joint_min_fraction_ppm"] == 857143
    assert report["free_exterior"]["joint_min_fraction_ppm"] == 0
    phase["prefill"] = 0
    assert (
        BOUND["price"](observed, phase, exterior)["full_client"]["joint_min_fraction_ppm"] is None
    )
    with pytest.raises(ValueError, match="exceeds"):
        BOUND["price"](observed, dict(phase, prefill=20_000_000_000), exterior)
