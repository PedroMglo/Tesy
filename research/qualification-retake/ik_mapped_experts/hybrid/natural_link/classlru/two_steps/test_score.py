from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))


def test_preceding_selection():
    ori = S["origin"]
    assert ori((2, 4, 1), (2, 3, 1)) == "previous_decode"
    assert ori((2, 5, 1), (2, 3, 1)) == "two_or_more_decode"
    assert ori((2, 3, 1), (2, 2, 5)) == "T2_prefill"
    assert ori((2, 2, 5), (1, 86, 1)) == "T1"


def test_class_age_and_pin():
    for policy in ("lru", "classlru"):
        bank = S["Bank"](8, policy)
        assert bank.plan(0, [0, 1, 2, 3] * 2) == ({0, 1, 2, 3}, 0)
        assert bank.plan(1, [0, 1, 2, 3]) == ({128, 129, 130, 131}, 0)
        assert bank.plan(0, [3, 2, 1, 4]) == ({4}, 1)
        if policy == "classlru":
            assert bank.clock[:2] == [3, 1] and bank.crf[3] > 1
        assert {1, 2, 3, 4} <= bank.group.keys()
