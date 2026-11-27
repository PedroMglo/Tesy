from pathlib import Path
from runpy import run_path

import pytest

STUDY = Path(__file__).resolve().parents[1] / "research/ready-experts/cpu_wave/supplied"
REVIEW = run_path(STUDY / "review.py")
BOUND = run_path(STUDY / "executor_bound.py")
LOOK = run_path(STUDY / "lookahead.py")
PRICE = run_path(STUDY / "service_price.py")
FRONT = run_path(STUDY / "frontier.py")


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


def test_future_read_owns_the_lane_and_waits_for_the_authoritative_region():
    job = LOOK["Job"]
    groups = [[job(0, 0, 4, 5)], [job(1, 1, 2, 3)]]
    assert LOOK["floor"](groups, 0) == LOOK["schedule"](groups, 0)[0] == 14
    end, info, (opening, packed) = LOOK["schedule"](groups, 1)
    assert LOOK["floor"](groups, 1) == end == 12
    assert opening == [0, 9, 12]
    assert (info["early_reads"], info["parked_buffer_peak"], info["worker_parked_ns"]) == (1, 1, 7)
    events = {i: data for i, *data in packed}
    events[1][3:] = [8, 11]
    with pytest.raises(ValueError, match="dependency"):
        LOOK["audit"](groups, 1, opening, events)


def test_empty_regions_and_four_occupied_workers():
    job = LOOK["Job"]
    groups = [[], [job(i, 1, 5, 2) for i in range(4)], [job(4, 2, 7, 3)], []]
    for lead in (0, 1):
        end, info, (opening, _) = LOOK["schedule"](groups, lead)
        assert end == 17
        assert LOOK["floor"](groups, lead) == (10 if lead else 17)
        assert opening == [0, 0, 7, 17, 17]
        assert info["early_reads"] == 0 and info["generations"] == 5


def test_required_read_price_obeys_both_integer_deadlines():
    limits = BOUND["LIMITS"]

    def cost(saving):
        return {
            "first_final": limits["first_final"] + 12 - saving,
            "decode": limits["decode"] + 41 - saving,
        }

    cut = PRICE["threshold"](cost)
    assert cut["min_read_reduction_ppm"] == 41
    assert cut["one_ppm_less_ns"]["decode"] == limits["decode"] + 1
    assert PRICE["threshold"](lambda _: limits)["min_read_reduction_ppm"] == 0
    assert PRICE["threshold"](lambda _: cost(40))["min_read_reduction_ppm"] is None


def test_two_regions_and_mixed_release_with_independent_scheduler():
    job = LOOK["Job"]
    groups = [[job(0, 0, 4, 5)], [job(1, 1, 2, 3)], [job(2, 2, 7, 1)]]
    for lead in (0, 1):
        assert FRONT["schedule"](groups, lead) == LOOK["schedule"](groups, lead)
    end, counts, _ = FRONT["schedule"](groups, 2)
    assert end == 13 and counts["early_reads"] == 2
    puts = {0: 5, 1: 3, 2: 1}
    mixed = FRONT["lower"](groups, {0: 0, 1: 1, 2: 0}, puts)
    assert FRONT["lower"](groups, {0: 0, 1: 0, 2: 0}, puts) == 13 < mixed == 15
