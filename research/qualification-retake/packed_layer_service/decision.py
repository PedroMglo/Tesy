"""Cost screen for a single five-generation service wave (not product latency)."""

from fractions import Fraction
from statistics import median

ORDERS = ("NSD", "SDN", "DNS", "DSN", "SND", "NDS")
LAYOUT = {"N": "DENSE", "S": "STAGED", "D": "DIRECT"}
CLOCKS = ("publish_ns", "resume_ns", "outer_ns")


def schedule():
    return [
        (block, LAYOUT[c], mode)
        for block, seq in enumerate(ORDERS, 1)
        for mode in (("MIN", "DETAIL") if block % 2 else ("DETAIL", "MIN"))
        for c in seq
    ]


def screen(arms):
    expected = schedule()
    if len(arms) != len(expected) or any(
        (a["block"], a["layout"], a["observer"]) != key
        for a, key in zip(arms, expected, strict=True)
    ):
        raise ValueError("incomplete_or_reordered_family")
    rows = {}
    for a in arms:
        if any(type(a.get(k)) is not int or a[k] <= 0 for k in CLOCKS):
            raise ValueError("nonpositive_or_noninteger_interval")
        rows[a["block"], a["layout"], a["observer"]] = a
    comparisons = {}
    for layout in ("STAGED", "DENSE"):
        metrics = {}
        for metric in ("publish_ns", "resume_ns"):
            gain = [
                1 - Fraction(rows[i, "DIRECT", "MIN"][metric], rows[i, layout, "MIN"][metric])
                for i in range(1, 7)
            ]
            metrics[metric] = dict(
                gains=list(map(float, gain)),
                median_gain=float(median(gain)),
                positive_pairs=sum(v > 0 for v in gain),
            )
            if metric == "publish_ns":
                metrics["publication_pass"] = (
                    median(gain) >= Fraction(5, 100) and sum(v > 0 for v in gain) >= 5
                )
            else:
                metrics["resume_pass"] = median(gain) > 0
        comparisons[layout] = metrics
    neutral = {}
    for layout in LAYOUT.values():
        tests = {}
        for metric in ("publish_ns", "outer_ns"):
            ratio = [
                Fraction(rows[i, layout, "DETAIL"][metric], rows[i, layout, "MIN"][metric])
                for i in range(1, 7)
            ]
            inside = sum(Fraction(85, 100) <= x <= Fraction(115, 100) for x in ratio)
            ok = Fraction(95, 100) <= median(ratio) <= Fraction(105, 100) and inside >= 5
            tests[metric] = dict(
                ratios=list(map(float, ratio)),
                median_ratio=float(median(ratio)),
                within_15pct=inside,
                passes=ok,
            )
        neutral[layout] = tests
    good = all(m["publication_pass"] and m["resume_pass"] for m in comparisons.values())
    detail = all(m["passes"] for metrics in neutral.values() for m in metrics.values())
    return dict(
        decision="GO_NEXT_SERVICE_SCOPE" if good else "NO_GO_FIVE_MISS_SERVICE_SCREEN",
        detail_class="QUALIFIED_DETAIL" if detail else "DIAGNOSTIC_PERTURBED_DETAIL",
        comparisons=comparisons,
        neutral=neutral,
    )
