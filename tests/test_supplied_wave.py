import itertools
import json
from pathlib import Path
from runpy import run_path

import pytest

STUDY = Path(__file__).resolve().parents[1] / "research/ready-experts/cpu_wave/supplied"
REVIEW = run_path(STUDY / "review.py")
BOUND = run_path(STUDY / "executor_bound.py")
LOOK = run_path(STUDY / "lookahead.py")
PRICE = run_path(STUDY / "service_price.py")
FRONT = run_path(STUDY / "frontier.py")
LIFE = run_path(STUDY / "slot_lifetime.py")
BANK = run_path(STUDY / "slot_bank.py")
PACK = run_path(STUDY / "slot_packing.py")


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


def test_public_natural_bounds_have_the_original_service_population_and_cuts():
    prior, one, price = (
        json.loads((STUDY / p).read_bytes())
        for p in ("bound.json", "lookahead.json", "service-price.json")
    )
    assert BOUND["sha"](STUDY / "bound.json") == one["parent_sha256"] == LOOK["PARENT"]
    assert BOUND["sha"](STUDY / "lookahead.json") == price["parent_sha256"] == FRONT["LOOK"]
    assert BOUND["sha"](STUDY / "service-price.json") == FRONT["PRICE"]
    for label, trace in prior["traces"].items():
        assert sum(trace["generations_by_consumer"].values()) == 2354
        for metric, phases in BOUND["PHASES"].items():
            assert (
                sum(trace["phases"][p]["span_ns"] for p in phases) + trace["outside_ns"][metric]
                == trace["observed_ns"][metric]
            )
            a = one["traces"][label]["1"]["clocks"][metric]
            assert a["lower_full_client_ns"] <= a["schedule_full_client_ns"]
            assert (
                price["traces"][label]["1"]["original_sets"]["current_floor_ns"][metric]
                == a["lower_full_client_ns"]
            )
        paid = price["traces"][label]["1"]["original_sets"]
        assert all(v <= BOUND["LIMITS"][k] for k, v in paid["at_cut_ns"].items())
        assert any(v > BOUND["LIMITS"][k] for k, v in paid["one_ppm_less_ns"].items())


def test_direct_slot_removes_only_the_copy_and_rejects_the_projection_permutation():
    receipt = json.loads((STUDY / "slot-result.json").read_bytes())
    assert receipt["status"] == "GO_CPU_RECORD_SLOT_FIXTURE_ONLY"
    assert receipt["model_forwards"] == receipt["gpu_forwards"] == 0
    for name, digest in receipt["sources"].items():
        assert BOUND["sha"](STUDY / name) == digest
    assert receipt["protocol_sha256"] == BOUND["sha"](STUDY / "slot-layout.md")
    assert receipt["retake_protocol_sha256"] == BOUND["sha"](STUDY / "slot-retake.md")

    arms = receipt["arms"]
    original = arms["A"]
    assert len(set(original["generation_sha256"])) == 2
    for role in ("A", "B", "C", "MUTANT"):
        row = arms[role]
        assert row["direct_reads"] == 5 and row["requested_bytes"] == 66109440
        assert row["bytes"] == 2 * (1 + 20 + 32) * 4 * 2880 * 3 * 4
        if role == "MUTANT":
            assert row["sha256"] != original["sha256"]
            assert set(row["generation_sha256"]).isdisjoint(original["generation_sha256"])
        else:
            assert row["sha256"] == original["sha256"]
            assert row["generation_sha256"] == original["generation_sha256"]
        expected_copies = (15, 66096000) if role in ("A", "B") else (0, 0)
        assert (row["weight_sets"], row["weight_set_payload_bytes"]) == expected_copies

    oracle = json.loads((STUDY / "composition.json").read_bytes())
    assert oracle["parent_sha256"] == BOUND["sha"](STUDY / "frontier.json")
    assert oracle["decision"] == "GO_TEMPORAL_FIXTURE_ONLY"
    for trace in oracle["traces"].values():
        for clock, budget in BOUND["LIMITS"].items():
            slack = budget - trace["near_free_cpu_set_schedule_ns"][clock]
            assert 0 < slack == trace["maximum_extra_schedule_ns"][clock]
        causal_floor = trace["four_t1_free_cpu_set_floor_ns"]["first_final"]
        assert causal_floor > BOUND["LIMITS"]["first_final"]


def test_slot_read_waits_for_prior_consumer_and_covers_the_measured_wave_gap():
    job = LIFE["Job"]
    jobs = [
        job(0, (0, 3, 1, 5), 0, 0, 0, 0, -1, -1, 3, 1),
        job(1, (0, 3, 2, 8), 0, 0, 1, 1, 0, 0, 2, 1),
    ]
    for gaps, expected in (([0, 0], 7), ([5, 0], 12)):
        witness = LIFE["schedule"](jobs, 0, gaps)
        LIFE["audit"](jobs, 0, gaps, witness)
        assert witness[0][-1] == expected
        edges = LIFE["interval_edges"](jobs, len(gaps))
        assert LIFE["graph_floor"](0, gaps, edges, 100) <= expected
    steps = witness[2]
    assert steps[1][2] == witness[0][1] == 9
    steps[1][2:4] = [7, 9]
    with pytest.raises(ValueError, match="victim still pinned"):
        LIFE["audit"](jobs, 0, [5, 0], witness)


def test_staged_cuda_read_can_overlap_the_old_use_and_the_cpu_parking_fence():
    job = LIFE["Job"]
    cpu = job(0, (0, 0, 3, 7), 1, 0, 1, 1, -1, 0, 7, 1)
    gpu = job(1, (25, 0, 3, 7), 1, 0, 1, 1, 0, 0, 7, 2)
    # FIFO within a deadline makes the parked CPU head a deliberate limit of the constructor.
    for jobs, expected_start in (([gpu], 0), ([cpu], 5)):
        path = LIFE["schedule"](jobs, 0, [5, 0])
        LIFE["audit"](jobs, 0, [5, 0], path)
        assert path[2][0][2] == expected_start
    jobs = [job(i, (0, i, 1, i), 0, 0, 0, 0, -1, -1, 4, 1) for i in range(5)]
    path = LIFE["schedule"](jobs, 0, [0])
    assert path[0][-1] == 10
    assert LIFE["graph_floor"](0, [0], LIFE["interval_edges"](jobs, 1), 0) == 7


def test_resident_hit_waits_for_reserve_and_only_a_known_miss_gets_earlier_release():
    job = LIFE["Job"]
    jobs = [job(i, (0, i, 1, i + 7), 2, 0, 5, 6, -1, -1, 11, 1) for i in range(3)]
    fixed = BANK["intervention"](jobs, {2: 4}, {1}, [[8]], "history_four", 50)
    assert [(j.read, j.horizon) for j in fixed] == [(0, 5), (6, 0), (6, 4)]
    assert [j.key for j in fixed] == [j.key for j in jobs]
    assert all(j.put == 1 and j.due == 6 for j in fixed)


def test_required_disk_discount_is_bracketed_by_adjacent_percentages():
    limits = BOUND["LIMITS"]
    cut = BANK["read_cut"](lambda pct: {k: limit - 64 + pct for k, limit in limits.items()})
    assert cut["min_saving_percent"] == 36
    assert cut["fits_ns"] == limits
    assert cut["one_percent_less_saving_ns"]["first_final"] == limits["first_final"] + 1
    assert BANK["read_cut"](lambda _: limits)["min_saving_percent"] == 0
    assert (
        BANK["read_cut"](lambda _: {"first_final": 10**12, "decode": 0})["min_saving_percent"]
        is None
    )


def test_independent_four_bin_checks_against_all_small_worker_assignments():
    for costs in ((5, 5, 5, 5, 5), (7, 7, 6, 5, 4, 4), (9, 8, 7, 6, 5, 3, 2)):
        best = sum(costs)
        for choices in itertools.product(range(4), repeat=len(costs) - 1):
            loads = [costs[0], 0, 0, 0]
            for i, lane in enumerate(choices, 1):
                loads[lane] += costs[i]
            best = min(best, max(loads))
        assert PACK["exact_four"](costs) == best
        assert PACK["fits_in_four"](costs, best)
        assert not PACK["fits_in_four"](costs, best - 1)


def test_stronger_certificate_rejects_an_invalid_extra_nanosecond():
    job = LIFE["Job"]
    jobs = [job(i, (0, i, 1, i), 0, 0, 0, 0, -1, -1, 4, 1) for i in range(5)]
    base, floor, path = PACK["path_floor"](jobs, 0, [0])
    assert (base, floor) == (7, 10)
    assert PACK["verify_call"](1, path) == (10, 1)
    bad = [list(step) for step in path]
    bad[0][3] += 1
    with pytest.raises(ValueError, match="impossible interval"):
        PACK["verify_call"](1, bad)
