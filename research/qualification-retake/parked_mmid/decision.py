"""Apply the registered paired gate to eight CPU0 FFN graph intervals."""

from statistics import median

ORDER = ("OFF", "ON", "ON", "OFF", "ON", "OFF", "OFF", "ON")
MIN_MEDIAN_GAIN_NS = 1_000_000


def evaluate(arms):
    if tuple(a["mode"] for a in arms) != ORDER:
        raise ValueError("incomplete or reordered schedule")
    if any(type(a["graph_ns"]) is not int or a["graph_ns"] <= 0 for a in arms):
        raise ValueError("invalid graph interval")

    pairs = []
    for i in range(0, len(arms), 2):
        by_mode = {a["mode"]: a["graph_ns"] for a in arms[i : i + 2]}
        off, on = by_mode["OFF"], by_mode["ON"]
        pairs.append(dict(off_ns=off, on_ns=on, saved_ns=off - on, on_over_off=on / off))
    savings = [p["saved_ns"] for p in pairs]
    center = median(savings)
    decision = "INCONCLUSIVE"
    if min(savings) > 0 and center >= MIN_MEDIAN_GAIN_NS:
        decision = "GO_TEST_NEXT"
    elif max(savings) <= 0:
        decision = "NO_GO_CPU0_TILE"
    return {
        "decision": decision,
        "pairs": pairs,
        "median_saved_ns": center,
        "min_saved_ns": min(savings),
        "max_saved_ns": max(savings),
    }
