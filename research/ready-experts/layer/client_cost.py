"""Check whether any witnessed common integer placement survives a free pre-stream interval."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(HERE / "all_banks.py")
B, C, SRC, need = (A[k] for k in ("B", "C", "SRC", "need"))
METHOD = "4554241880ba678857c93f3a5f477164eb475c66d026723e925076662644b1d1"
CREDIT = 646_428_255


def search(data, active, direct):
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, linprog, milp
    from scipy.sparse import block_diag, csc_matrix, hstack, vstack

    shared = len(active)
    models = [A["linear_model"](regs, active, direct) for regs, _ in data.values()]
    matrices = [model[1] for model in models]
    common = vstack([m[:, :shared] for m in matrices])
    own = block_diag([m[:, shared:] for m in matrices])
    base = hstack((common, own, csc_matrix((own.shape[0], 1))), format="csc")
    constraints = [base]
    rhs = [x for m in models for x in m[2]]
    bounds = [(0, 1)] * shared
    for regs_ext, model in zip(data.items(), models, strict=True):
        label, (regs, ext) = regs_ext
        offset = len(bounds) - shared
        wall = [i + offset for i, x in enumerate(model[0]) if x == 1]
        call_numbers = [n for n, gs, _ in regs for _ in gs]
        need(len(wall) == len(call_numbers), "one wall per group")
        bounds.extend(model[3][shared:])
        for name, limit in (("first_final", B["FIRST_LIMIT"]), ("decode", B["DECODE_LIMIT"])):
            filt = [
                j
                for n, j in zip(call_numbers, wall, strict=True)
                if (n <= 46 if name == "first_final" else n >= 3)
            ]
            credit = CREDIT if name == "first_final" and label == "P106" else 0
            rhs.append((limit + credit - ext[name]) / 1e6)
            row = csc_matrix(
                ([1] * len(filt) + [-1], ([0] * (len(filt) + 1), filt + [base.shape[1] - 1])),
                shape=(1, base.shape[1]),
            )
            constraints.append(row)
    bounds.append((None, None))
    need(len(bounds) == base.shape[1], "common selector extent")
    mat = vstack(constraints, format="csc")
    cost = np.zeros(mat.shape[1])
    cost[-1] = 1
    lp = linprog(cost, A_ub=mat, b_ub=rhs, bounds=bounds, method="highs")
    need(lp.success, "joint LP")

    def top(x):
        return sorted(
            active[i] for i in sorted(range(shared), key=lambda i: (-float(x[i]), active[i]))[:353]
        )

    banks = {"rounded": top(lp.x)}
    integer = np.zeros(len(cost))
    integer[:shared] = 1
    limits = Bounds(
        [lo if lo is not None else -np.inf for lo, _ in bounds],
        [hi if hi is not None else np.inf for _, hi in bounds],
    )
    mip = milp(
        cost,
        integrality=integer,
        constraints=LinearConstraint(mat, -np.inf, rhs),
        bounds=limits,
        options={"time_limit": 30.0},
    )
    if mip.x is not None and np.max(np.abs(np.rint(mip.x[:shared]) - mip.x[:shared])) < 1e-5:
        banks["integer"] = [k for i, k in enumerate(active) if mip.x[i] > 0.5]
    return banks


def assess(data, chosen, direct):
    arms = {}
    for label, (regs, exterior) in data.items():
        clocks = dict(exterior)
        for tag, groups, edges in regs:
            costs = []
            for g in groups:
                prices = [
                    (0 if direct else j.set_ns) if j.expert in chosen else j.read_ns + j.set_ns
                    for j in g.jobs
                ]
                costs.append(B["layer_fourths"](prices))
            wall, _ = C["cuts"]([4 * g.internal for g in groups], [4 * v for v in edges], costs)
            duration = (wall + 3) // 4
            if tag <= 46:
                clocks["first_final"] += duration
            if tag >= 3:
                clocks["decode"] += duration
        arms[label] = clocks
    required = max(0, arms["P106"]["first_final"] - B["FIRST_LIMIT"])
    protected = B["joint"](arms["P97"]) >= 0 and arms["P106"]["decode"] <= B["DECODE_LIMIT"]
    return {
        "with_full_client_cost_ns": arms,
        "p106_first_needed_credit_ns": required,
        "p106_full_grant_first_ns": arms["P106"]["first_final"] - CREDIT,
        "other_three_clocks_pass": protected,
        "fits_with_grant": protected and required <= CREDIT,
    }


def run(a):
    need(SRC["digest"](HERE / "client-cost.md") == METHOD, "prospective protocol")
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    need(prior["P106"]["pre_stream_allowance_ns"] == CREDIT, "client allowance")
    data = {}
    for name in ("P106", "P97"):
        regs, auth, keys, _ = C["load_arm"](a.archive, name, prior[name])
        if name == "P106":
            offered = keys
        for _, groups, _ in regs:
            for g in groups:
                g.jobs.sort(key=lambda j: (j.expert, j.read_ns, j.set_ns))
        data[name] = (regs, auth["outside_calls_ns"])
    seen = {j.expert for regs, _ in data.values() for _, gs, _ in regs for g in gs for j in g.jobs}
    active = sorted(seen & offered)
    witnesses = json.loads(a.verify.read_bytes()) if a.verify else {}
    results = {}
    for mode in ("copied", "direct"):
        if not a.verify:
            witnesses[mode] = search(data, active, mode == "direct")
        entries = {}
        need(
            witnesses[mode] and set(witnesses[mode]) <= {"rounded", "integer"}, "solver candidates"
        )
        for label, keys in witnesses[mode].items():
            bank = set(map(tuple, keys))
            need(len(keys) == len(bank) <= 353 and bank <= offered, "witness capacity or origin")
            entry = assess(data, bank, mode == "direct")
            entry["bank_sha256"] = hashlib.sha256(
                json.dumps(sorted(bank), separators=(",", ":")).encode()
            ).hexdigest()
            entries[label] = entry
        results[mode] = entries
    if not a.verify:
        (a.new_output_dir / "banks.json").write_text(
            json.dumps(witnesses, sort_keys=True, separators=(",", ":")) + "\n"
        )
    return {
        "schema": "tesy.ready_client_cost.v1",
        "status": "TRACE_DERIVED",
        "credit_ns": CREDIT,
        "protocol_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "results": results,
        "decisions": {
            m: "EXISTS_WITH_HYPOTHETICAL_CREDIT"
            if any(v["fits_with_grant"] for v in entries.values())
            else "INCONCLUSIVE"
            for m, entries in results.items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(args)
    except FileNotFoundError as exc:
        p = Path(exc.filename).resolve()
        report = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if p.is_relative_to(args.archive.resolve())
            else "FAIL",
            "missing": p.name,
        }
    except (ValueError, KeyError, ImportError, OSError, AssertionError) as exc:
        report = {"status": "FAIL", "reason": str(exc)}
    tmp = args.new_output_dir / ".pending"
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.rename(args.new_output_dir / "receipt.json")
    print(report["status"], report.get("decisions", report.get("reason", "")))
    raise SystemExit(report["status"] != "TRACE_DERIVED")
