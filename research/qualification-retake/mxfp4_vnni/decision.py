"""Evaluate the preregistered paired elapsed times. Every operand is an integer ns."""

from fractions import Fraction


def evaluate(arms):
    groups = []
    i = 0
    for cpu in (0, 4):
        for regime in ("hot", "stream"):
            count, repeats = (64, 4096) if regime == "hot" else (23040, 12)
            section = arms[i : i + 6]
            if len(section) != 6:
                raise ValueError("incomplete array of arms")
            for index, (row, variant) in enumerate(zip(section, "RABBAR", strict=True), 1):
                expected = (cpu, regime, index, variant, count, repeats)
                observed = tuple(
                    row[k] for k in ("cpu", "regime", "arm", "variant", "rows", "repeats")
                )
                if (
                    expected != observed
                    or type(row["duration_ns"]) is not int
                    or row["duration_ns"] <= 0
                ):
                    raise ValueError("work, arm order or clock")
            durations = [r["duration_ns"] for r in section]
            pairs = []
            for r, a, b in ((0, 1, 2), (5, 4, 3)):
                against_a = Fraction(durations[a] - durations[b], durations[a])
                against_r = Fraction(durations[r] - durations[b], durations[r])
                pairs.append(
                    dict(
                        r=r + 1,
                        a=a + 1,
                        b=b + 1,
                        reduction_vs_A=float(against_a),
                        reduction_vs_R=float(against_r),
                        passed=min(against_a, against_r) >= Fraction(1, 10),
                    )
                )
            groups.append(dict(cpu=cpu, regime=regime, pairs=pairs))
            i += 6
    if i != len(arms):
        raise ValueError("extra arm")
    passed = all(p["passed"] for g in groups for p in g["pairs"])
    return {
        "decision": "GO_ROUTED_MMID_FIXTURE" if passed else "NO_GO_GLOBAL_KERNEL_PROMOTION",
        "groups": groups,
        "threshold_reduction": 0.10,
    }
