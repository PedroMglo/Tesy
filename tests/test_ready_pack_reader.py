from pathlib import Path
from runpy import run_path

import pytest

RUN = run_path(
    Path(__file__).resolve().parents[1] / "research/ready-experts/renewal/reader/physical.py"
)


def transcript(first, second):
    rows = ["fd 1 2 3 4 5"]
    for arm in range(30):
        mode = ("PRE", "RING")[arm % 2 if arm < 16 else 1 - arm % 2]
        for group in range(4):
            ratio = first if arm < 16 else second
            price = ratio[group // 2] if mode == "RING" else 1_000_000
            rows.append(f"{arm} {mode} {group} {4 if group < 2 else 1} {price}")
    return [*rows, "drained"]


def test_reader_grade_uses_paired_strata_and_two_orders():
    key = [1, 2, 3, 4, 5]
    good, close, poor = 731182, 731183, 1000001
    grade = RUN["grade"](transcript([good, good], [good, good]), key)
    assert grade["decision"] == "GO_SERVICE_PROFILE" and grade["verified_component_hashes"] == 900
    assert (
        RUN["grade"](transcript([good, close], [close, good]), key)["decision"]
        == "NO_GO_UNIFORM_CUT_THIS_FIXTURE"
    )
    mixed = RUN["grade"](transcript([good, good], [good, poor]), key)
    assert mixed["decision"] == "INCONCLUSIVE" and mixed["local_gain"] == "INCONCLUSIVE"
    with pytest.raises(ValueError):
        RUN["grade"](transcript([good, good], [good, good])[:-1], key)
