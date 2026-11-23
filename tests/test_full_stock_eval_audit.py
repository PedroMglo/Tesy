import pytest

from tesy.full_stock_eval_audit import resource_peaks, upper_median_p95


def test_upper_median_nearest_rank_p95():
    assert upper_median_p95([5, 1, 4, 2, 3]) == {"median": 3, "p95": 5}


def test_resource_peaks_excludes_terminal_processless_row():
    rows = [
        {"gpu": {"status": "OK", "memory_used_bytes": 10,
                 "temperature_c": 40.0, "power_w": 12.0},
         "process": {"VmRSS_bytes": 100, "VmSwap_bytes": 0}},
        {"gpu": {"status": "OK", "memory_used_bytes": 11,
                 "temperature_c": 41.0, "power_w": 12.0}, "process": {}},
    ]
    result = resource_peaks(rows)
    assert result["valid_process_samples"] == 1
    assert result["terminal_samples_without_process"] == 1
    assert result["peak_process_swap_bytes"] == 0


def test_resource_peaks_fail_closed_on_swap():
    rows = [{"gpu": {"status": "OK", "memory_used_bytes": 10,
                     "temperature_c": 40.0, "power_w": 12.0},
             "process": {"VmRSS_bytes": 100, "VmSwap_bytes": 4096}}]
    with pytest.raises(ValueError, match="swap"):
        resource_peaks(rows)
