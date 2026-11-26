"""Check both admission orders, including ghost loss, reinsertion and boundary state."""

from collections import Counter
from itertools import product
from pathlib import Path
from runpy import run_path

R = run_path(str(Path(__file__).with_name("replay.py")))


def test_ghost_protects_a_reused_key_and_forgets_a_cold_key():
    bank = R["Bank"](2, "SECOND_MISS")
    counts = Counter()
    for key in (0, 0, 1, 2, 3, 0, 1):
        bank.request(key, counts)
    assert list(bank.resident) == [0]
    assert list(bank.waiting) == [3, 1]
    assert counts == dict(requests=7, hits=1, misses=6, admits=1, bypass=5)


def test_exhaustive_small_prefixes_match_an_independent_list_machine():
    for mode, cap, sequence in product(R["MODES"], (1, 2), product(range(3), repeat=5)):
        bank = R["Bank"](cap, mode)
        counts = Counter()
        ready, ghost = [], []
        misses = 0
        for key in sequence:
            bank.request(key, counts)
            if key in ready:
                ready = [k for k in ready if k != key] + [key]
            else:
                misses += 1
                if mode == "LRU" or key in ghost:
                    ghost = [k for k in ghost if k != key]
                    ready = (ready + [key])[-cap:]
                else:
                    ghost = (ghost + [key])[-cap:]
            assert (list(bank.resident), list(bank.waiting)) == (ready, ghost)
            assert counts["misses"] == misses
        assert bank.state()[:2] == [len(ready), len(ghost)]
