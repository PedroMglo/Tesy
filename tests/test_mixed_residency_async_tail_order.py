import json
from pathlib import Path

import pytest

from tesy.mixed_residency_async_tail_order import (
    MixedResidencyAsyncTailOrderError,
    analyze_async_tail_order_raw,
    analyze_conditioned_case,
)


def _conditioned_series(
    *,
    steady_serial: float = 1.0,
    steady_async: float = 0.85,
    transition_async: float = 2.0,
) -> tuple[list[float], list[float]]:
    serial = [1.05] * 81
    async_values = [transition_async] * 81

    # Odd samples are async-first and therefore async-after-async.
    for index in range(1, 81, 2):
        async_values[index] = steady_async

    # Even serial samples >= 2 are serial-after-serial.
    for index in range(2, 81, 2):
        serial[index] = steady_serial

    return serial, async_values


def test_conditioned_tail_go_ignores_serial_to_async_transition_spikes():
    serial, async_values = _conditioned_series()

    row = analyze_conditioned_case(
        serial,
        async_values,
        gpu_hits=2,
    )

    assert row["median_gate_pass"] is True
    assert row["p95_gate_pass"] is True
    assert row["steady_async_median_ratio_vs_serial"] == pytest.approx(0.85)
    assert row["steady_async_p95_ratio_vs_serial"] == pytest.approx(0.85)
    assert (
        row["serial_to_async_p95_amplification_vs_steady_async"]
        > 2.0
    )


def test_conditioned_tail_no_go_when_steady_async_p95_regresses():
    serial, async_values = _conditioned_series()

    # There are 40 odd async-after-async observations. Three high values are
    # sufficient to move the frozen nearest-rank p95 while leaving the median
    # at the low steady value.
    for index in (1, 3, 5):
        async_values[index] = 1.30

    row = analyze_conditioned_case(
        serial,
        async_values,
        gpu_hits=3,
    )

    assert row["median_gate_pass"] is True
    assert row["p95_gate_pass"] is False
    assert row["steady_async_median_ratio_vs_serial"] == pytest.approx(0.85)
    assert row["steady_async_p95_ratio_vs_serial"] == pytest.approx(1.30)


def test_h1_is_control_not_decision_gate():
    serial, async_values = _conditioned_series(
        steady_async=0.95,
        transition_async=1.0,
    )

    row = analyze_conditioned_case(
        serial,
        async_values,
        gpu_hits=1,
    )

    assert row["gated"] is False
    assert row["median_gate_pass"] is None
    assert row["p95_gate_pass"] is None


def test_conditioned_case_requires_exact_81_samples():
    serial, async_values = _conditioned_series()

    with pytest.raises(
        MixedResidencyAsyncTailOrderError,
        match="81 samples",
    ):
        analyze_conditioned_case(
            serial[:-1],
            async_values,
            gpu_hits=2,
        )


def test_published_21_sample_campaign_cannot_satisfy_tail_gate():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (
            root
            / "research"
            / "results"
            / "mixed-residency-async-overlap-20260924T152625Z"
            / "raw.json"
        ).read_text(encoding="utf-8")
    )

    with pytest.raises(
        MixedResidencyAsyncTailOrderError,
        match="81 samples",
    ):
        analyze_async_tail_order_raw(payload)
