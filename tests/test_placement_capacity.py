import json
from pathlib import Path

import pytest

from tesy.placement_capacity import (
    MIB,
    PlacementCapacityError,
    evaluate_capacity,
    parse_fit_print,
    parse_fitted_cli,
)


def test_parse_fitted_cli_accepts_frozen_stock_arguments():
    payload = parse_fitted_cli(
        '-c 4096 -ngl 25 -ot "blk\\.13\\.ffn_(up|down)_exps=CPU"\n',
        expected_ctx=4096,
    )
    assert payload["ctx_size"] == 4096
    assert payload["n_gpu_layers"] == 25
    assert payload["argv"] == [
        "-c",
        "4096",
        "-ngl",
        "25",
        "-ot",
        r"blk\.13\.ffn_(up|down)_exps=CPU",
    ]


def test_parse_fitted_cli_rejects_unknown_flag():
    with pytest.raises(PlacementCapacityError, match="unexpected fitted CLI flag"):
        parse_fitted_cli("-c 4096 -ngl 25 --foo bar\n", expected_ctx=4096)


def test_parse_fitted_cli_rejects_context_change():
    with pytest.raises(PlacementCapacityError, match="changed frozen context"):
        parse_fitted_cli("-c 8192 -ngl 25\n", expected_ctx=4096)


def test_parse_fit_print_accepts_one_device_plus_host():
    rows = parse_fit_print(
        "CUDA0 6000 200 300\n"
        "Host 5000 0 100\n"
    )
    assert rows["CUDA0"]["total_mib"] == 6500
    assert rows["Host"]["total_mib"] == 5100


def test_parse_fit_print_ignores_non_table_logging():
    rows = parse_fit_print(
        "build: test log line\n"
        "CUDA0 6000 200 300\n"
        "Host 5000 0 100\n"
    )
    assert set(rows) == {"CUDA0", "Host"}


def test_evaluate_capacity_requires_headroom():
    payload = evaluate_capacity(
        "CUDA0 6000 200 300\nHost 5000 0 100\n",
        gpu_free_bytes=7600 * MIB,
        mem_available_bytes=10000 * MIB,
        n_cpu_moe=12,
        gpu_target_mib=1024,
        host_guard_mib=2048,
        rounding_guard_mib=16,
    )
    assert payload["gpu_required_mib"] == 7540
    assert payload["host_required_mib"] == 7164
    assert payload["admitted"] is True


def test_evaluate_capacity_rejects_gpu_shortfall():
    payload = evaluate_capacity(
        "CUDA0 6000 200 300\nHost 5000 0 100\n",
        gpu_free_bytes=7500 * MIB,
        mem_available_bytes=10000 * MIB,
        n_cpu_moe=8,
    )
    assert payload["admitted"] is False
    assert payload["rejection_reasons"] == ["PROJECTED_GPU_HEADROOM"]
