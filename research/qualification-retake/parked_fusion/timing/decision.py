"""Apply the prospectively frozen three-treatment CPU0 graph gate."""

from fractions import Fraction
from statistics import median

MODES = ("ORIGINAL", "MMID", "FUSION")
BLOCKS = tuple(
    tuple(MODES[int(i)] for i in order) for order in ("012", "120", "201", "210", "102", "021")
)
ORDER = sum(BLOCKS, ())


def evaluate(rows):
    if tuple(r["mode"] for r in rows) != ORDER:
        raise ValueError("incomplete or reordered timing blocks")
    if any(type(r["graph_ns"]) is not int or r["graph_ns"] <= 0 for r in rows):
        raise ValueError("invalid graph interval")
    blocks, versus_original, versus_mmid, relative = [], [], [], []
    for i, order in enumerate(BLOCKS):
        times = {r["mode"]: r["graph_ns"] for r in rows[3 * i : 3 * i + 3]}
        o, m, f = (times[key] for key in MODES)
        versus_original.append(o - f)
        versus_mmid.append(m - f)
        relative.append(Fraction(o - f, o))
        blocks.append(
            dict(
                order=list(order),
                original_ns=o,
                mmid_ns=m,
                fusion_ns=f,
                original_minus_fusion_ns=o - f,
                mmid_minus_fusion_ns=m - f,
                fusion_over_original=f / o,
                fusion_over_mmid=f / m,
            )
        )
    center_o = median(relative)
    center_m = median(versus_mmid)
    decision = "INCONCLUSIVE"
    if (
        min(versus_original) > 0
        and min(versus_mmid) > 0
        and center_o >= Fraction(1, 20)
        and center_m >= 1_000_000
    ):
        decision = "GO_DIVERSE_TILES"
    elif max(versus_original) <= 0 or max(versus_mmid) <= 0:
        decision = "NO_GO_CPU0_TILE"
    return dict(
        decision=decision,
        blocks=blocks,
        median_relative_gain_vs_original=float(center_o),
        median_original_minus_fusion_ns=median(versus_original),
        median_mmid_minus_fusion_ns=center_m,
        range_original_minus_fusion_ns=[min(versus_original), max(versus_original)],
        range_mmid_minus_fusion_ns=[min(versus_mmid), max(versus_mmid)],
    )
