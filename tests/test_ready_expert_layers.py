from itertools import combinations, product
from pathlib import Path
from runpy import run_path

import pytest

HERE = Path(__file__).resolve().parents[1] / "research/ready-experts/layer"
C = run_path(HERE / "causality.py")
A = run_path(HERE / "all_banks.py")
Region, Job = C["Region"], C["R"]["Job"]


@pytest.mark.parametrize(
    ("inside", "gaps", "service"),
    [
        ([1, 2, 0], [0, 3, 7, 2], [10, 0, 9]),
        ([0, 1], [2, 1, 3], [3, 0]),
        ([2], [4, 3], [7]),
    ],
)
def test_cut_matches_all_partitions_and_boundary_allocations(inside, gaps, service):
    observed, selected = C["cuts"](inside, gaps, service)

    def cut(bits):
        paid = sum(s if on else g for on, s, g in zip(bits, service, inside, strict=True))
        return paid + sum(
            gap
            for i, gap in enumerate(gaps)
            if not (i and bits[i - 1]) and not (i < len(bits) and bits[i])
        )

    assert (
        observed == cut(selected) == max(cut(bits) for bits in product((0, 1), repeat=len(inside)))
    )
    minimum = None
    for split in product(*(range(g + 1) for g in gaps[1:-1])):
        left = [gaps[0]] + [g - s for g, s in zip(gaps[1:-1], split, strict=True)]
        right = [*split, gaps[-1]]
        wall = sum(
            max(s, a + b + g) for s, a, b, g in zip(service, left, right, inside, strict=True)
        )
        minimum = wall if minimum is None else min(minimum, wall)
    assert observed == minimum


@pytest.mark.parametrize("direct", (False, True))
def test_supports_and_integer_certificate_hold_for_every_bank(monkeypatch, direct):
    D = A["D"]
    offered = {(0, i) for i in range(4)}
    monkeypatch.setitem(A["R"], "BUDGET", 2)
    js = [Job((0, i), r, s) for i, (r, s) in enumerate([(20, 4), (23, 1), (19, 2), (15, 3)])]
    regs = [
        Region((1, 0, i), v, jobs)
        for i, (v, jobs) in enumerate([(1, js), (8, js[:2]), (3, js[2:])])
    ]
    gaps = [4, 8, 3, 1]
    calls = [(1, regs, gaps)]
    parts = [[D // 4, D // 4, D // 2, 0, 0, 0], [D // 2, D // 4, 0, D // 4], [D // 2, 0, D // 2, 0]]
    cert = A["verify"](calls, offered, 42, [[1, parts]], direct=direct, limit=81)["floor_ns"]
    for n in range(3):
        for keys in combinations(sorted(offered), n):
            bank = set(keys)
            prices = []
            for g in regs:
                a, h = C["affine"](g.jobs, bank)
                value = a - sum(h[k] for k in bank)
                prices.append(
                    C["B"]["layer_fourths"](
                        [
                            (0 if direct else j.set_ns)
                            if j.expert in bank
                            else j.set_ns + j.read_ns
                            for j in g.jobs
                        ]
                    )
                )
                assert value == C["B"]["layer_fourths"](
                    [j.set_ns + (0 if j.expert in bank else j.read_ns) for j in g.jobs]
                )
                for other in offered:
                    assert a - h[other] <= C["B"]["layer_fourths"](
                        [j.set_ns + (0 if j.expert == other else j.read_ns) for j in g.jobs]
                    )
            lower, _ = C["cuts"]([4 * g.internal for g in regs], [4 * v for v in gaps], prices)
            assert cert <= 42 + (lower + 3) // 4
    parts[1][1] += 1
    with pytest.raises(ValueError, match="convex weights"):
        A["verify"](calls, offered, 42, [[1, parts]], direct=direct, limit=81)


def test_client_allowance_is_confined_to_one_first_final():
    candidate = run_path(HERE / "client_cost.py")
    limit = C["B"]["FIRST_LIMIT"]
    credit = candidate["CREDIT"]
    job = Job((0, 0), 80, 20)
    regs = [(n, [Region((n, 0, 0), 0, [job])], [0, 0]) for n in (2, 3, 47)]

    def assess(p97):
        data = {
            "P106": (regs, {"first_final": limit + credit - 200, "decode": 0}),
            "P97": (regs, {"first_final": p97, "decode": 0}),
        }
        return candidate["assess"](data, set(), False)

    accepted = assess(0)
    assert accepted["fits_with_grant"] and accepted["p106_first_needed_credit_ns"] == credit
    assert accepted["with_full_client_cost_ns"]["P97"] == {"first_final": 200, "decode": 200}
    assert not assess(limit - 199)["fits_with_grant"]
