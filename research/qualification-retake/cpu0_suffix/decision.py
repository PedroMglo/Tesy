"""Descriptive paired analysis after the supervisor verifies the eight CPU0 arms."""

from fractions import Fraction
from statistics import median

ORDER = ("OFF", "ON", "ON", "OFF", "ON", "OFF", "OFF", "ON")
LOW = Fraction(85, 100)
HIGH = Fraction(115, 100)


def positive_ns(value):
    return type(value) is int and value > 0


def evaluate(arms):
    """Report the measured ON suffix and the identifiable OFF interval in nanoseconds."""
    rows = list(arms)
    if len(rows) != len(ORDER):
        raise ValueError("eight arms required")
    for i, (row, mode) in enumerate(zip(rows, ORDER, strict=True)):
        if type(row.get("run_index")) is not int or row["run_index"] != i:
            raise ValueError("run_index must be chronological and zero-based")
        if row.get("observer") != mode or not positive_ns(row.get("graph_ns")):
            raise ValueError("observer order or graph clock")
        suffix = row.get("suffix_ns")
        if mode == "ON" and (not positive_ns(suffix) or suffix > row["graph_ns"]):
            raise ValueError("missing ON suffix or suffix outside graph clock")
        if mode == "OFF" and suffix is not None:
            raise ValueError("OFF cannot observe the suffix")

    pairs = []
    graph_ratios, suffixes = [], []
    for i in range(0, len(rows), 2):
        a, b = rows[i:i + 2]
        off, on = (a, b) if a["observer"] == "OFF" else (b, a)
        ratio = Fraction(on["graph_ns"], off["graph_ns"])
        graph_ratios.append(ratio)
        suffixes.append(on["suffix_ns"])
        pairs.append(dict(
            off_index=off["run_index"], on_index=on["run_index"],
            off_graph_ns=off["graph_ns"], on_graph_ns=on["graph_ns"],
            on_over_off_graph_ratio=float(ratio),
            on_before_marker_ns=on["graph_ns"] - on["suffix_ns"],
            on_suffix_ns=on["suffix_ns"],
            off_suffix_identified_interval_ns=[0, off["graph_ns"]],
        ))
    middle = median(Fraction(s) for s in suffixes)
    graph_within_band = all(LOW <= r <= HIGH for r in graph_ratios)
    suffix_within_band = all(LOW * middle <= s <= HIGH * middle for s in suffixes)
    return dict(
        status=("REPRODUCED_ON_SUFFIX_IN_CPU0_FIXTURE"
                if graph_within_band and suffix_within_band
                else "INCONCLUSIVE_OBSERVER_OR_DISPERSION"),
        paired_graphs_within_band=graph_within_band, on_suffixes_within_band=suffix_within_band,
        on_suffix_ns=dict(min=min(suffixes), median=float(middle), max=max(suffixes)),
        on_over_off_graph_median_ratio=float(median(graph_ratios)),
        pairs=pairs, off_suffix_point_estimate_ns=None,
        c135_nonoverlapped_compute_floor_ns=None,
    )
