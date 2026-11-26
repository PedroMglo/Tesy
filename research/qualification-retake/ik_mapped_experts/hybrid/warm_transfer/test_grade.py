import copy
from pathlib import Path
from runpy import run_path

import pytest

G = run_path(str(Path(__file__).with_name("grade.py")))
OFFSETS, SLAB = G["OFFSETS"], G["SLAB"]


def control():
    residues = [x % 4096 for x in OFFSETS]
    pages = [(SLAB + x + 4095) // 4096 for x in residues]
    rows = []
    for i, m in enumerate(
        [
            "FILE",
            "ANON",
            "FILE",
            "ANON",
            "ANON",
            "FILE",
            "FILE",
            "ANON",
            "ANON",
            "FILE",
            "FILE",
            "ANON",
        ]
    ):
        wall = 1000000 if m == "FILE" else 2000000
        rows.append(
            dict(
                mode=m,
                exact=i < 2,
                pages_before=pages[:],
                pages_after=pages[:],
                copies=3,
                payload_B=3 * SLAB,
                poison_B=576,
                roundtrip_B=3 * SLAB if i < 2 else 576,
                major_faults=0,
                minor_faults=1,
                input_blocks=0,
                wall_ns=wall,
                submit_ns=1000,
                drain_ns=wall - 1000,
                thread_ns=4000,
                process_ns=4500,
            )
        )
    return dict(
        status="PASS_HOT_TRANSFER_PROCESS",
        order="FILE_FIRST",
        offsets=OFFSETS,
        residues=residues,
        span_B=sum(pages) * 4096,
        rows=rows,
    )


def test_reciprocal_and_pair():
    d = control()
    r = G["grade"](d["order"], d)
    assert r["paired_FILE_minus_ANON_ns"] == [-1000000] * 5
    assert r["measurements"]["FILE"]["aggregate_B_s"] == 13_219_200_000
    assert all(r["measurements"]["FILE"]["cuts_at_median"].values())
    assert not any(r["measurements"]["ANON"]["cuts_at_median"].values())
    for row in d["rows"]:
        row["mode"] = "ANON" if row["mode"] == "FILE" else "FILE"
    d["order"] = "ANON_FIRST"
    assert G["grade"](d["order"], d)["median_paired_ns"] == 1000000


@pytest.mark.parametrize(
    "key,value",
    [
        ("pages_after", [1076, 1077, 1077]),
        ("input_blocks", 1),
        ("roundtrip_B", 0),
        ("copies", 2),
        ("wall_ns", 432),
        ("major_faults", 1),
        ("mode", "FILE"),
        ("exact", True),
    ],
)
def test_faults(key, value):
    d = copy.deepcopy(control())
    d["rows"][3][key] = value
    with pytest.raises(ValueError):
        G["grade"](d["order"], d)


def test_registration_or_wrong_stride():
    d = control()
    with pytest.raises(ValueError):
        G["grade"](d["order"], d, "REG 1 1234 4406400 -1 0 0")
    d["residues"][1] = 0
    with pytest.raises(ValueError):
        G["grade"](d["order"], d)
