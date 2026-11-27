from pathlib import Path
from runpy import run_path

STUDY = Path(__file__).resolve().parents[1] / "research/ready-experts/cpu_wave/code_chat"
SELECTION = run_path(STUDY / "price/selection/run.py")


def test_selection_needs_two_complete_agreeing_past_successors():
    eligible = SELECTION["eligible"]
    target = [4, 5]
    once = [7, 8, 4, 5, 7, 8]
    assert not eligible(once, target)
    assert eligible(once + [4, 5, 7, 8], target)
    assert not eligible(once + [4, 5, 7, 8, 4, 6, 7, 8], target)
    assert not eligible(once + [4, 5, 7, 8], [5, 4])


def test_observed_price_and_selection_cut_inside_a_block():
    steps = [
        dict(at=1, proposal=[7, 8], accepted=2, emitted=3),
        dict(at=4, proposal=[], accepted=0, emitted=1),
    ]
    result = SELECTION["pair"](steps, [True, False], [0, 10, 20, 30, 40], [0, 30, 30, 30, 47], 1)
    assert result["first_final_native"]["filter_gain_ns"] == -20
    assert result["first_final_native"]["oracle_gain_ns"] == 0
    assert result["full"]["filter_gain_ns"] == 0
    assert result["full"]["ordinary_gain_ns"] == -7


def test_public_numerics_and_natural_cost_have_separate_reproducible_gates():
    cuts = run_path(STUDY / "block/review.py")
    price = SELECTION["REVIEW"]
    cuts["check"](cuts["read"](STUDY / "block/result.json"))
    result = price["read"](STUDY / "price/result.json")
    price["compact"](result)
    assert result["cut_sha256"] == price["F"]["NUMERIC"]
    assert result["protocol_sha256"] == price["sha"](STUDY / "price/protocol.md")


def test_recorded_projection_references_and_causal_prices_are_bound_to_their_inputs():
    read, sha = SELECTION["read"], SELECTION["sha"]
    rank_path = STUDY / "observed_rank"
    rank = read(rank_path / "result.json")
    assert rank["protocol_sha256"] == sha(rank_path / "protocol.md")
    assert rank["program_sha256"] == sha(rank_path / "run.py")
    assert rank["logical_gguf_bytes"] == 3 * 4_406_400
    assert set(rank["stages"]) == {"gate", "up", "down"}
    for variant in ("layout", "layout_and_q8"):
        unequal = sum(
            lib[variant]["different_bits"]
            for stage in rank["stages"].values()
            for lib in stage["builds"].values()
        )
        expected = "NO_GO_EXACT_DROP_IN_AT_OBSERVED_RANK" if unequal else "GO_FULL_RANK_FIXTURE"
        assert rank["decision"][variant] == expected
    folder = STUDY / "price/selection"
    selected = read(folder / "result.json")
    assert selected["review_sha256"] == sha(STUDY / "price/result.json")
    assert selected["protocol_sha256"] == sha(folder / "protocol.md")
    assert selected["program_sha256"] == sha(folder / "run.py")
    positive = all(
        v["filter_gain_ns"] > 0 for pair in selected["comparison"].values() for v in pair.values()
    )
    assert selected["decision"] == ("GO_SELECTIVE_FIXTURE" if positive else "NO_GO_THIS_FILTER")
