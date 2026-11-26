"""Re-evaluate integer bounds and feasible witnesses for the fixed T1 bank."""

import argparse
import importlib.util
import itertools
import os
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("individual_bank", HERE / "screen.py")
bank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank)
src = bank.source
need = src.need
FIRST = "fafd225a2bc8bfeefbb431a21e768aa32eb49f2faa94ee2afe5606677c4c0083"
METHOD = "8dad72b27e7fdc834055b083ce471adaf7fb199194b6966952641fc1653851c2"
SOLVER = Path("/usr/bin/lp_solve")
SOLVER_SHA = "2a127a82646d682d6db1bc9f398b4e41484afcde8804fca2f55c9613fa267eaf"
K = 353


class Option(NamedTuple):
    keys: tuple
    b: int
    h: int
    gain: int


def options(groups, allowed, volume, hits):
    seen, out = set(), []
    for group in groups:
        members = {k for k, _ in group}
        need(len(members) == len(group) and not seen & members, "disjoint first groups")
        seen |= members
        candidates = sorted(members & allowed)
        need(len(candidates) <= 10, "group enumeration limit")
        if not candidates:
            continue
        cold = bank.opportunity.floor([t for _, t in group])
        choices = []
        for n in range(1, len(candidates) + 1):
            for keys in itertools.combinations(candidates, n):
                rest = bank.opportunity.floor([t for k, t in group if k not in keys])
                choices.append(
                    Option(
                        keys, sum(volume[k] for k in keys), sum(hits[k] for k in keys), cold - rest
                    )
                )
        out.append(choices)
    for k in sorted(allowed - seen):
        if volume[k] or hits[k]:
            out.append([Option((k,), volume[k], hits[k], 0)])
    return out


def simple(eligible, volumes, hits, cap, required_b, required_h):
    def bound(price):
        keys = sorted(eligible, key=lambda k: (-(volumes[k] + price * hits[k]), k))[:cap]
        actual = sum(volumes[k] + price * hits[k] for k in keys)
        wanted = required_b + price * required_h
        return wanted - actual, sum(hits[k] for k in keys), price, actual, wanted

    lo, hi = 0, 1
    while hi < 2**40 and bound(hi)[1] < required_h:
        hi *= 2
    while hi - lo > 1:
        mid = (hi + lo) // 2
        if bound(mid)[1] >= required_h:
            hi = mid
        else:
            lo = mid
    gap, _, price, upper, required = max((bound(i) for i in {0, lo, hi}), key=lambda t: t[0])
    return dict(hit_price=price, upper=upper, required=required, deficit=gap)


def certificate(opts, cap, req_b, req_h, prices):
    """For any feasible selection, D*gain + pb*req_b + ph*req_h <= upper."""
    d, pb, ph, pc = prices
    need(d > 0 and min(pb, ph, pc) >= 0, "dual prices")
    upper = pc * cap
    for group in opts:
        upper += max(0, max(d * o.gain + pb * o.b + ph * o.h - pc * len(o.keys) for o in group))
    return (upper - pb * req_b - ph * req_h) // d


def term(factors):
    return " + ".join(f"{v:.12f} x{i}" for i, v in factors if v) or "0"


def model(opts, k, bytes_, hits, target=None):
    numbered = [[(i, o) for i, o in g] for g in number(opts)]
    flat = [z for line in numbered for z in line]
    us = 10**6
    gain = term((i, o.gain / us) for i, o in flat)
    lines = [
        f"max: {gain};",
        "kc: " + term((i, len(o.keys)) for i, o in flat) + f" <= {k};",
        "bv: " + term((i, o.b / us) for i, o in flat) + f" >= {bytes_ / us:.12f};",
        "hd: " + term((i, o.h) for i, o in flat) + f" >= {hits};",
    ]
    for line in numbered:
        lines.append(term((i, 1) for i, _ in line) + " <= 1;")
    if target is not None:
        lines.append(f"{gain} >= {target / us:.12f};")
        lines.append("bin " + ", ".join(f"x{i}" for i, _ in flat) + ";")
    return "\n".join(lines) + "\n"


def number(opts):
    i = 0
    for group in opts:
        yield list(enumerate(group, i))
        i += len(group)


def solve_lp(opts, cap, req_b, req_h, target=None):
    # The solver supplies candidate prices/sets only. Never accept its verdict.
    detail = "-S4" if target is None else "-S2"
    flags = [] if target is None else ["-f"]
    try:
        proc = subprocess.run(
            [str(SOLVER), detail, *flags, "-timeout", "10"],
            input=model(opts, cap, req_b, req_h, target),
            text=True,
            capture_output=True,
            timeout=13,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, (1000, 0, 0, 0), "TIME_LIMIT"
    need(proc.returncode in (0, 1, 2, 7, 12), f"solver failure {proc.returncode}")
    vals, duals = {}, {}
    section = ""
    for line in proc.stdout.splitlines():
        if line.startswith("Dual values"):
            section = "duals"
        elif line.startswith("Actual values of the variables"):
            section = "vars"
        elif line.startswith(("Actual values of the constraints", "Objective function limits")):
            section = ""
        fields = line.split()
        if len(fields) < 2:
            continue
        key, val = fields[:2]
        if section == "vars" and key.startswith("x") and key[1:].isdigit():
            vals[int(key[1:])] = float(val)
        if section == "duals" and key in ("kc", "bv", "hd"):
            duals[key] = abs(Fraction(val))
    # Gains in ms; volume in decimal MB, count and cardinality unscaled.
    prices = (
        1000,
        round(1000 * duals.get("bv", 0)),
        round(10**9 * duals.get("hd", 0)),
        round(10**9 * duals.get("kc", 0)),
    )
    return vals, prices, f"EXIT_{proc.returncode}"


def rounding(opts, vals):
    fixed, frac = set(), []
    for line in number(opts):
        positive = [(vals.get(i, 0), o.keys) for i, o in line if vals.get(i, 0) > 1e-8]
        if not positive:
            continue
        if len(positive) == 1 and positive[0][0] >= 1 - 1e-7:
            fixed.update(positive[0][1])
            continue
        alts = [keys for _, keys in sorted(positive, key=lambda x: (-x[0], x[1]))]
        if sum(v for v, _ in positive) < 1 - 1e-7:
            alts.append(())
        frac.append(alts)
    for config in itertools.islice(itertools.product(*frac), 512):
        yield fixed.union(*config)


def max_residual(fixed, a, b):
    return ((10**10 - fixed + 1) * b - 1) // a


def run(args):
    need(
        src.sha(HERE / "joint.md") == METHOD and src.sha(SOLVER) == SOLVER_SHA,
        "protocol and solver",
    )
    first = src.pinned(args.first_dir / "receipt.json", FIRST)
    local = src.pinned(args.local_dir / "receipt.json", bank.LOCAL)
    seal = src.pinned(args.prepared_dir / "receipt.json", local["prepared_sha256"])
    need(
        src.sha(args.prepared_dir / "selection.json")
        == seal["selection_sha256"]
        == first["selection_sha256"]
        and first["program_sha256"] == src.sha(HERE / "screen.py"),
        "escrow and frozen individual screen",
    )
    inp = src.load_inputs(args.part, args.model, args.inventory, args.prepared_dir)
    need(inp.journal == first["journal_sha256"], "local process")
    start = int(inp.client["request_started_monotonic"] * 1e9)
    final = start + int(inp.client["stream_metrics"]["first_final_content_chunk_s"] * 1e9)
    plan, base = bank.replay.planner.assemble(inp.rows, inp.meta, start, final)
    groups = bank.replay.oracle.jobs({"groups": plan}, inp.rows)
    v, p, h = bank.totals(inp.rows)
    eligible = set(map(tuple, inp.available["evicted_ready"]))
    ref = first["rows"][0]["witnesses"]["time"]
    need(
        base == ref["raw_floor_ns"]
        and v.total() == first["baseline_return_bytes"]
        and h.total() == first["decode_jobs"]
        and bank.replay.host.additional(K) < inp.memory
        and bank.opportunity.source.digest(sorted(eligible)) == first["population_sha256"],
        "frozen controls",
    )
    opts = options(groups, eligible, v, h)
    fixed = first["fixed_ns"]
    need_hits = (h.total() + 4) // 5
    result = {}
    for label in ("47", "46"):
        req = v.total() - first["budgets"][label]
        both = simple(eligible, v, h, K, req, need_hits)
        cases = {}
        result[label] = {"simple": both, "scales": cases}
        if both["deficit"] > 0:
            for sc in ("1/1", "4/5"):
                cases[sc] = {"decision": "NO_GO_INTEGER_VOLUME_AND_HITS"}
            continue
        xs, prices, lp = solve_lp(opts, K, req, need_hits)
        upper = certificate(opts, K, req, need_hits, prices)
        for a, b in ((1, 1), (4, 5)):
            needed = base - max_residual(fixed, a, b)
            item = {
                "decision": "INCONCLUSIVE",
                "required_gain_ns": needed,
                "gain_upper_ns": upper,
                "upper_minus_required_ns": upper - needed,
                "dual_prices": list(prices),
                "lp_status": lp,
            }
            cases[f"{a}/{b}"] = item
            if upper < needed:
                item["decision"] = "NO_GO_INTEGER_WAVE_CERTIFICATE"
                continue
            for method in ("lp_rounding", "binary"):
                candidates = xs
                if method == "binary":
                    candidates, _, status = solve_lp(opts, K, req, need_hits, needed)
                    item["mip_status"] = status
                for keys in rounding(opts, candidates):
                    if len(keys) > K:
                        continue
                    keys = keys | bank.top(eligible - keys, v, K - len(keys))
                    need(len(keys) == K and keys <= eligible, "candidate identity")
                    w = bank.witness(keys, v, p, h, groups, fixed)
                    if (
                        w["prefill_return_bytes_saved"] >= req
                        and w["decode_hits"] >= need_hits
                        and base - w["raw_floor_ns"] >= needed
                    ):
                        need(
                            upper >= base - w["raw_floor_ns"],
                            "certificate excludes a feasible witness",
                        )
                        item.update(
                            decision="HEADROOM_ONLY_PRICE_COPIES",
                            witness=w,
                            selection_method=method,
                            selected_keys=sorted(keys),
                        )
                        break
                if "witness" in item:
                    break
    # Keep identifiers private. The reproducible full configurations and their
    # hashes allow a third party with access to the same archive to reprice them.
    selected = {
        f"{n}-{scale}": case.pop("selected_keys")
        for n, row in result.items()
        for scale, case in row["scales"].items()
        if "selected_keys" in case
    }
    bank.opportunity.save(args.new_output_dir / "witnesses.json", selected)
    return dict(
        status="PASS_JOINT_STATIC_SCREEN",
        first_sha256=FIRST,
        local_sha256=bank.LOCAL,
        journal_sha256=inp.journal,
        solver_sha256=SOLVER_SHA,
        groups=len(opts),
        nonempty_options=sum(map(len, opts)),
        decode_hits_required=need_hits,
        witnesses_sha256=src.sha(args.new_output_dir / "witnesses.json"),
        rows=result,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in (
        "first-dir",
        "part",
        "model",
        "inventory",
        "prepared-dir",
        "local-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + n, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = run(a)
    except Exception as err:
        r = {"status": "FAIL_PRESERVED", "error": f"{type(err).__name__}: {err}"}
    r.update(program_sha256=src.sha(Path(__file__)), protocol_sha256=METHOD)
    bank.opportunity.save(a.new_output_dir / "receipt.json", r)
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
