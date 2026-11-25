import copy
import runpy
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
G = runpy.run_path(str(HERE / "grade.py"))


def trial():
    rows = []
    for wave in range(8):
        for role in range(3):
            for lane in range(8):
                tick = 101 + 100 * (3 * wave + role) + lane
                rows.append([wave, role, lane, 8, 1000 + lane, 4 + lane, 4 + lane, tick, tick + 10])
    return dict(
        rows=rows,
        on=True,
        start_ns=99,
        end_ns=2500,
        publish_ns=10,
        compute_masks={str(1000 + i): [4 + i] for i in range(8)},
        fresh_hits=5,
        hot_reads=0,
        hot_sets=0,
    )


def test_wall_vs_thread_and_epoch():
    x = trial()
    r = G["iteration"](x, "A", True, {50, 51, 52, 53}, list(range(24)))
    assert r["mmid_union_ns"] == 24 * 17
    assert r["active_wave_union_ns"] == 3 * 17
    assert r["summed_lane_wall_ns"] == 192 * 10
    assert r["different_cpu_endpoints"] == 0
    errors = []
    for key in ("hot_reads", "hot_sets"):
        errors.append(dict(x, **{key: 1}))
    duplicate = copy.deepcopy(x)
    duplicate["rows"][2] = duplicate["rows"][1]
    errors.extend([duplicate, dict(x, end_ns=2400), dict(x, compute_masks={"1000": [4, 5]})])
    for value in errors:
        with pytest.raises(ValueError):
            G["iteration"](value, "A", True, {50, 51, 52, 53}, list(range(24)))


def test_neutrality_precedes_placement():
    arms = [
        dict(
            team=m,
            stock=i == 0,
            slots=[],
            graph=[24],
            off_median_ns=t,
            on_over_off=None if i == 0 else 1.0,
        )
        for i, (m, t) in enumerate(zip("RRABBAR", [100, 101, 110, 80, 79, 109, 99], strict=True))
    ]
    d = G["decision"](arms)
    assert d["contrasts"]["R_minus_B"] == dict(delta_ns=[21, 20], direction="B_SHORTER")
    assert d["contrasts"]["A_minus_B"]["delta_ns"] == [30, 30]
    arms[2]["on_over_off"] = 1.151
    assert G["decision"](arms)["contrasts"] == {}
    arms[2]["on_over_off"] = 1
    arms[0]["off_median_ns"] = 150
    assert G["decision"](arms)["status"] == "INCONCLUSIVE_OBSERVER"
