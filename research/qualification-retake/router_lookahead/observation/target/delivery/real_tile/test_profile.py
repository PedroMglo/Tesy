"""Model-free regressions for the family gate and both signed pairs."""

from pathlib import Path
from runpy import run_path

import pytest

P = run_path(str(Path(__file__).with_name("profile.py")))


def valid():
    keys = [(0, e) for e in range(66)] + [(1, e) for e in range(59)]
    return dict(
        status="PASS_REAL_TILE",
        grade="EXACT",
        mode="OFF",
        workers=4,
        drained=True,
        offers=P["OFFERS"],
        read_jobs=125,
        pread_bytes=125 * P["WINDOW"],
        reads=[[a, b, 0, i, i + 1] for i, (a, b) in enumerate(keys)],
        sets=375,
        slab_hashes=375,
        slot_bindings=[[a, b, b % 40, 1 + b // 40] for a, b in keys],
        numeric={"0": "fixture", "1": "fixture"},
        elapsed_ns=500,
        producer_ns=1,
        drain_ns=1,
        wait_ns=1,
        stage={"issued": 0},
        epochs_ns=[1, 2],
        service=[1],
    )


def test_exact_control_conservation():
    row = valid()
    assert P["check_row"](row, "EXACT", "OFF") == (row["numeric"], row["slot_bindings"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("drained", False),
        ("workers", 3),
        ("sets", 374),
        ("slab_hashes", 372),
        ("pread_bytes", 1),
        ("offers", [42]),
    ],
)
def test_incomplete_arms_cannot_admit_timing(field, value):
    with pytest.raises(ValueError):
        P["check_row"](valid() | {field: value}, "EXACT", "OFF")


def test_unauthorized_read_is_not_an_off_arm():
    row = valid()
    row["reads"][0][2] = 1
    with pytest.raises(ValueError):
        P["check_row"](row, "EXACT", "OFF")


def test_lost_slot_is_detected_even_with_right_totals():
    row = valid()
    row["slot_bindings"][-1] = row["slot_bindings"][-2]
    with pytest.raises(ValueError):
        P["check_row"](row, "EXACT", "OFF")


def test_timing_excludes_bulk_hashing():
    row = valid() | {"grade": "TIME"}
    with pytest.raises(ValueError):
        P["check_row"](row, "TIME", "OFF")
    P["check_row"](row | {"slab_hashes": 0}, "TIME", "OFF")


@pytest.mark.parametrize(
    "clocks,expected",
    [
        ([12, 9, 11, 14], "GO_NEXT_PAIR_FIXTURE"),
        ([9, 12, 14, 11], "NO_GO_TRAVERSAL_TIMING"),
        ([9, 12, 11, 14], "INCONCLUSIVE_TRAVERSAL_TIMING"),
        ([9, 9, 11, 14], "INCONCLUSIVE_TRAVERSAL_TIMING"),
    ],
)
def test_order_and_ties(clocks, expected):
    rows = [
        {"grade": g, "mode": m, "elapsed_ns": ns}
        for (g, m), ns in zip(P["ORDER"], [400, 500, *clocks], strict=True)
    ]
    assert P["paired"](rows) == ([clocks[0] - clocks[1], clocks[3] - clocks[2]], expected)
    with pytest.raises(ValueError):
        P["paired"](rows[2:])


def test_independent_gold_rejects_a_changed_mask_despite_equal_final_ffn():
    rows = {}
    files = {}
    for layer in range(2):
        tag = f"L{layer}"
        row = dict(
            layer=layer, ffn_words=92160, mmid_nodes=24, bias_nodes=24, active_waves=4, waves=[]
        )
        rows[tag] = row
        for field, suffix in (
            ("ffn", "ffn.f32"),
            ("x", "x.f32"),
            ("mix", "mix.f32"),
            ("logical", "ids.i32"),
        ):
            row[field + "_sha256"] = files[f"{tag}.{suffix}"] = f"{tag}{field}"
        for i in range(8):
            wave = dict(wave=i, active=32 if i < 4 else 0, parking_differences=0)
            for field, suffix in (
                ("physical", "ids.i32"),
                ("generation", "gen.u64"),
                ("mask", "mask.f32"),
            ):
                wave[field + "_sha256"] = files[f"{tag}.w{i}.{suffix}"] = f"{tag}{i}{field}"
            row["waves"].append(wave)
    P["check_golds"](rows, files)
    rows["L1"]["waves"][4]["mask_sha256"] = "wrong"
    with pytest.raises(ValueError, match="wave digest"):
        P["check_golds"](rows, files)
