from pathlib import Path
from runpy import run_path

P = run_path(str(Path(__file__).with_name("review.py")))["price"]


def test_exact_boundary_no_rate_rounding():
    r = P(10, 1, 2, 50_000_000, 250_000_000, 5)
    assert r["fits_median"] and r["fits_aggregate"] and r["remaining_ns_at_median"] == 0
    r = P(10, 1, 2, 50_000_001, 250_000_001, 5)
    assert not r["fits_median"] and not r["fits_aggregate"]
    assert r["remaining_ns_at_median"] == -10


def test_budget_is_for_47_outputs_and_aggregate_uses_all_five():
    r = P(4706, 47, 6, 1_610_000, 8_500_000, 5)
    assert r["seconds_num"] == 47 and r["seconds_den"] == 6
    assert r["fits_median"] and not r["fits_aggregate"]
