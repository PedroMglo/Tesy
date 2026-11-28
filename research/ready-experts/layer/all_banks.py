"""Certify a lower bound for every 353-key bank with integer arithmetic."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(HERE / "causality.py")
R, B, SRC, need = (C[k] for k in ("R", "B", "SRC", "need"))
D = 1_000_000
METHOD = "455b7dfe89acdfeb8914ac26ffe7c3387e16f095f19fe8c3978464f44889bd26"


def weights(dual):
    # Zero is also a supporting plane. The verifier only needs nonnegativity and
    # a sum <= D. Discard residual and roundoff instead of trusting a solver tolerance.
    parts = [int(math.floor(D * max(0.0, -float(y)))) for y in dual]
    excess = max(0, sum(parts) - D)
    for i in sorted(range(len(parts)), key=lambda i: -parts[i]):
        take = min(excess, parts[i])
        parts[i] -= take
        excess -= take
    return parts


def verify(calls, offered, exterior, proof, *, direct, limit):
    """Independent of SciPy. Each row mixes graph, job-by-job and four-lane mean prices."""
    need(type(proof) is list and len(calls) == len(proof), "certificate call count")
    constant = 4 * D * exterior
    credit = Counter()
    for (call, groups, gaps), (tag, rows) in zip(calls, proof, strict=True):
        need(
            call == tag and len(rows) == len(groups) and len(gaps) == len(groups) + 1,
            "certificate sites",
        )
        for i, (g, parts) in enumerate(zip(groups, rows, strict=True)):
            need(
                len(parts) == 2 + len(g.jobs)
                and all(type(v) is int and v >= 0 for v in parts)
                and sum(parts) <= D,
                "invalid convex weights",
            )
            graph, mean, *individual = parts
            constant += 4 * graph * g.internal
            if i == 0:
                constant += 4 * graph * gaps[0]
            if i + 1 == len(groups):
                constant += 4 * graph * gaps[-1]
            if i:
                constant += 4 * min(graph, rows[i - 1][0]) * gaps[i]
            for j, m in zip(g.jobs, individual, strict=True):
                scale = mean + 4 * m
                constant += scale * (j.set_ns + j.read_ns)
                credit[j.expert] += scale * (j.read_ns + (j.set_ns if direct else 0))
    ordered = sorted((credit[k] for k in offered), reverse=True)
    saved = sum(ordered[: R["BUDGET"]])
    first_capacity = 0
    credit_at_capacity = 0
    while constant - credit_at_capacity > 4 * D * limit and first_capacity < len(ordered):
        credit_at_capacity += ordered[first_capacity]
        first_capacity += 1
    return {
        "floor_ns": (constant - saved + 4 * D - 1) // (4 * D),
        "first_capacity_not_excluded_by_this_certificate": first_capacity
        if constant - credit_at_capacity <= 4 * D * limit
        else None,
    }


def linear_model(calls, active, direct):
    # Unknowns are fractional bank membership, per-group wall and the share of
    # each external boundary assigned to its left neighbour. Time units here are ms.
    from scipy.sparse import coo_matrix

    key_index = {k: i for i, k in enumerate(active)}
    c = [0.0] * len(active)
    bounds = [(0, 1)] * len(active)
    ii, jj, values, rhs = [], [], [], []
    sites = []

    def add_var(price, limit):
        c.append(price)
        bounds.append((0, limit))
        return len(c) - 1

    def row(terms, upper):
        for var, value in terms:
            ii.append(len(rhs))
            jj.append(var)
            values.append(value)
        rhs.append(upper)

    row([(i, 1) for i in range(len(active))], R["BUDGET"])
    for tag, groups, gaps in calls:
        order = []
        left = None
        for i, g in enumerate(groups):
            t = add_var(1, None)
            right = add_var(0, gaps[i + 1] / 1e6) if i + 1 < len(groups) else None
            start = len(rhs)
            terms = [(t, -1)]
            fixed = g.internal + gaps[i]
            if left is not None:
                terms.append((left, -1))
            if right is not None:
                terms.append((right, 1))
            else:
                fixed += gaps[-1]
            row(terms, -fixed / 1e6)
            left = right
            # The average and each individual mandatory job are simultaneous lower bounds.
            jobs = sorted(g.jobs, key=lambda j: (j.expert, j.read_ns, j.set_ns))
            need(jobs == g.jobs, "canonical job order")
            for slice_, scale in [(jobs, 0.25)] + [([j], 1.0) for j in jobs]:
                terms = [(t, -1)]
                price = 0
                for j in slice_:
                    price += (j.read_ns + j.set_ns) * scale
                    if j.expert in key_index:
                        refundable = j.read_ns + (j.set_ns if direct else 0)
                        terms.append((key_index[j.expert], -refundable * scale / 1e6))
                row(terms, -price / 1e6)
            order.append((start, len(rhs)))
        sites.append((tag, order))
    A = coo_matrix((values, (ii, jj)), shape=(len(rhs), len(c))).tocsc()
    return c, A, rhs, bounds, sites


def propose(calls, offered, direct):
    from scipy.optimize import linprog

    active = sorted(offered & {j.expert for _, gs, _ in calls for g in gs for j in g.jobs})
    c, A, rhs, bounds, sites = linear_model(calls, active, direct)
    solution = linprog(c, A_ub=A, b_ub=rhs, bounds=bounds, method="highs")
    need(solution.success, "LP proposal unavailable")
    dual = solution.ineqlin.marginals
    return [[tag, [weights(dual[lo:hi]) for lo, hi in order]] for tag, order in sites]


def run(archive, new, existing):
    import gzip
    import hashlib

    need(
        SRC["digest"](HERE / "protocol.md") == C["METHOD"]
        and SRC["digest"](HERE / "certificate.md") == METHOD,
        "protocol",
    )
    SRC["pinned"](HERE.parent / "existence-result.json", C["PARENT"])
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    cert = json.loads(gzip.decompress(existing.read_bytes())) if existing else {}
    results = {}
    for k in ("P106", "P97"):
        regs, auth, keys, _ = C["load_arm"](archive, k, prior[k])
        if k == "P106":
            offered = keys
        for _, gs, _ in regs:
            for g in gs:
                g.jobs.sort(key=lambda j: (j.expert, j.read_ns, j.set_ns))
        results[k] = {}
        for mode in ("copied", "direct"):
            results[k][mode] = {}
            for name, limit in (("first_final", B["FIRST_LIMIT"]), ("decode", B["DECODE_LIMIT"])):
                eligible = [
                    item
                    for item in regs
                    if (item[0] <= 46 if name == "first_final" else item[0] >= 3)
                ]
                label = k + "_" + mode + "_" + name
                if not existing:
                    cert[label] = propose(eligible, offered, mode == "direct")
                results[k][mode][name] = verify(
                    eligible,
                    offered,
                    auth["outside_calls_ns"][name],
                    cert[label],
                    direct=mode == "direct",
                    limit=limit,
                )
    need(len(cert) == 8, "unexpected certificate")
    raw = gzip.compress((json.dumps(cert, separators=(",", ":")) + "\n").encode(), mtime=0)
    if not existing:
        (new / "proof.json.gz").write_bytes(raw)
    else:
        raw = existing.read_bytes()
    return {
        "status": "FORMAL_CONDITIONAL_ON_TRACE_PRICES",
        "schema": "tesy.layer_bank_certificate.v1",
        "clock_unit": "ns",
        "capacity": R["BUDGET"],
        "denominator": D,
        "arms": results,
        "protocol_sha256": C["METHOD"],
        "addendum_sha256": METHOD,
        "certificate_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": SRC["digest"](Path(__file__)),
        "decisions": {
            mode: "NO_GO_ALL_FIXED_BANKS"
            if any(
                B["joint"]({n: v["floor_ns"] for n, v in arm[mode].items()}) < 0
                for arm in results.values()
            )
            else "INCONCLUSIVE_ALL_BANKS"
            for mode in ("copied", "direct")
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    p.add_argument("--verify", type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(a.archive, a.new_output_dir, a.verify)
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve()
        report = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if missing.is_relative_to(a.archive.resolve())
            else "FAIL",
            "missing": missing.name,
        }
    except (ValueError, KeyError, TypeError, OSError, ImportError, AssertionError) as exc:
        report = {"status": "FAIL", "reason": str(exc)}
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(report["status"], report.get("decisions", report.get("reason", "")))
    raise SystemExit(report["status"] != "FORMAL_CONDITIONAL_ON_TRACE_PRICES")
