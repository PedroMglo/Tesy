"""Apply the four-row protocol to the complete mirrored timing journal."""

from fractions import Fraction

ORDER = "RACBBCAR"


def evaluate(arms):
    if len(arms) != 32:
        raise ValueError("expected 32 arms")
    groups = []
    for cpu in (0, 4):
        for regime, count, repeats in (("hot", 64, 4096), ("stream", 23040, 12)):
            start = len(groups) * 8
            section = arms[start : start + 8]
            for index, (row, variant) in enumerate(zip(section, ORDER, strict=True), 1):
                keys = ("cpu", "regime", "arm", "variant", "rows", "repeats")
                if tuple(row[k] for k in keys) != (cpu, regime, index, variant, count, repeats):
                    raise ValueError("work, case or arm order changed")
                if (
                    any(
                        type(row[k]) is not int
                        for k in ("cpu", "arm", "rows", "repeats", "duration_ns")
                    )
                    or row["duration_ns"] <= 0
                ):
                    raise ValueError("invalid arm types or duration")
            pairs = []
            for ri, ai, ci, bi in ((0, 1, 2, 3), (7, 6, 5, 4)):
                r, a, c, b = (section[i]["duration_ns"] for i in (ri, ai, ci, bi))
                ba, br = Fraction(a - b, a), Fraction(r - b, r)
                ca, cr = Fraction(a - c, a), Fraction(r - c, r)
                bc = Fraction(c - b, c)
                pairs.append(
                    dict(
                        r=ri + 1,
                        a=ai + 1,
                        c=ci + 1,
                        b=bi + 1,
                        B_vs_A=float(ba),
                        B_vs_R=float(br),
                        C_vs_A=float(ca),
                        C_vs_R=float(cr),
                        B_vs_C=float(bc),
                        B_pass=min(ba, br) >= Fraction(1, 10),
                        C_pass=min(ca, cr) >= Fraction(1, 10),
                        sharing_pass=bc >= Fraction(2, 100),
                    )
                )
            reductions = {
                k: {"min": min(p[k] for p in pairs), "max": max(p[k] for p in pairs)}
                for k in ("B_vs_A", "B_vs_R", "C_vs_A", "C_vs_R", "B_vs_C")
            }
            groups.append(dict(cpu=cpu, regime=regime, pairs=pairs, reduction_ranges=reductions))
    pairs = [p for g in groups for p in g["pairs"]]
    b_ok = all(p["B_pass"] for p in pairs)
    c_ok = all(p["C_pass"] for p in pairs)
    sharing = all(p["sharing_pass"] for p in pairs)
    decision = "NO_GO_FOUR_ROWS"
    if c_ok:
        decision = "GO_ROUTED_MMID_C_FIXTURE"
    if b_ok:
        decision = "GO_ROUTED_MMID_B_FIXTURE"
    return dict(
        decision=decision,
        shared_B_MMID_gate=b_ok,
        separate_C_MMID_gate=c_ok,
        sharing_at_least_2pct_all_pairs=sharing,
        groups=groups,
        threshold_operator=0.10,
        threshold_sharing=0.02,
    )
