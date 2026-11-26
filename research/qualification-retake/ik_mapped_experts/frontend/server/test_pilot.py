"""The ik adapter accepts only internally consistent, unambiguous native prompt counts."""

from pathlib import Path
from runpy import run_path

import pytest

P = run_path(str(Path(__file__).resolve().with_name("pilot.py")))


@pytest.mark.parametrize(("cache", "processed"), [(0, 2043), (2044, 153)])
def test_native_counts_do_not_mutate_the_journal(cache, processed):
    t = {"prompt_n": processed}
    usage = {"prompt_tokens": cache + processed, "prompt_tokens_details": {"cached_tokens": cache}}
    assert P["normalize"](usage, t, cache + processed) == {"prompt_n": processed, "cache_n": cache}
    assert t == {"prompt_n": processed}


@pytest.mark.parametrize(
    ("cached", "timing", "count"),
    [
        (True, {"prompt_n": 2}, 3),
        (2044, {"prompt_n": 152}, 2197),
        (2044, {"prompt_n": 153, "cache_n": 2044}, 2197),
    ],
)
def test_reject_ambiguous_or_wrong_native_counts(cached, timing, count):
    with pytest.raises(ValueError, match="native prompt accounting"):
        P["normalize"](
            {"prompt_tokens": count, "prompt_tokens_details": {"cached_tokens": cached}},
            timing,
            count,
        )
