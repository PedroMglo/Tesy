"""Capacity certificates via integer evaluation of untrusted coverage-weight allocations."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "score.py"))
check, digest, serialize = S["check"], S["Q"]["digest"], S["serialized"]
PPM, CAP, CLOCKS = S["PPM"], S["CAP"], S["CLOCKS"]
OLD = "677e2da38828aebee2747c1064ce81725ac4f97b298c3ef8d7c4be77785d9b59"
PROTO = "7d511b37e9bb5ca080847f5be02e308df18110f07f423e463da3a50eec44b998"
SOURCE = "e6d62af52c886042088c7346fd8e6fe52cf965d22e5a246922878574b0add9ee"
LP_SHA = "2a127a82646d682d6db1bc9f398b4e41484afcde8804fca2f55c9613fa267eaf"
LIB_SHA = "53848fb69737c6603d1fd0a74654d71629c9f629cf7c004b70e4fda399eef0c6"
SUPPORTS = ("never_offered", "all_jobs_support", "never_offered_support", "official_support")


def weighted(events, offered, bank, scale, mode):
    check(mode in SUPPORTS, "unexpected service support")
    ref = {"never_offered_support": offered, "official_support": bank}.get(mode, set())
    features = Counter()
    for e in events:
        base, bonuses = S["support"](e, scale, offered, ref, mode)
        features[tuple(sorted(e.sources))] += base
        for k, b in bonuses.items():
            features[(k,)] += b
    return sorted((k, v) for k, v in features.items() if v > 0)


def verify(features, shares, cap):
    """No solver needed. Check the proposed integers and calculate the universal upper bound."""
    check(len(features) == len(shares), "feature positions")
    free = 0
    loads = Counter()
    for (keys, value), d in zip(features, shares, strict=True):
        check(type(d) is int and 0 <= d <= value, "invalid partition in ns")
        free += value - d
        for key in keys:
            loads[key] += d
    return free + sum(sorted(loads.values(), reverse=True)[:cap])


def propose(features, cap):
    """Only the solver proposal is in milliseconds. Verify the objective independently in ns."""
    single = Counter()
    multiple = []
    for i, (keys, ns) in enumerate(features):
        if len(keys) == 1:
            single[keys[0]] += ns
        else:
            multiple.append((i, keys, ns))
    shares = [ns if len(keys) == 1 else 0 for keys, ns in features]
    if not multiple:
        return shares
    by_key = {}
    for i, keys, _ in multiple:
        for key in keys:
            by_key.setdefault(key, []).append(i)
    keys = sorted(single.keys() | by_key.keys())
    # Milliseconds make the objective readable; output weights are clamped and audited in ns.
    lines = [
        f"min: {cap} lim "
        + " ".join(f"+ v{j}" for j in range(len(keys)))
        + " "
        + " ".join(f"- d{i}" for i, _, _ in multiple)
        + ";"
    ]
    for j, key in enumerate(keys):
        pos = " ".join(f"+ d{i}" for i in by_key.get(key, ()))
        lines.append(f"{pos} - lim - v{j} <= {-single[key] / 1e6:.6f};")
    lines.extend(f"d{i} <= {w / 1e6:.6f};" for i, _, w in multiple)
    result = subprocess.run(
        ["/usr/bin/lp_solve", "-S2"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=8,
        env={"LC_ALL": "C"},
    )
    values = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("d") and parts[0][1:].isdigit():
            i = int(parts[0][1:])
            check(i not in values, "duplicate LP suggestion")
            values[i] = round(Decimal(parts[1]) * 1_000_000)
    check(values.keys() == {i for i, _, _ in multiple}, "missing LP suggestion")
    for i, _, w in multiple:
        shares[i] = min(w, max(0, values[i]))
    return shares


def evaluate(events, offered, bank, scale, cap, existing):
    if existing is not None:
        features = weighted(events, offered, bank, scale, existing["support"])
        return verify(features, existing["shares"], cap), existing
    best = None
    for mode in SUPPORTS if scale else SUPPORTS[:1]:
        features = weighted(events, offered, bank, scale, mode)
        shares = propose(features, cap)
        upper = verify(features, shares, cap)
        if best is None or upper < best[0]:
            best = (upper, {"support": mode, "shares": shares})
    return best


def frontier(clocks):
    def upper(s):
        vals = []
        for v in clocks.values():
            bound = v["upper_ns"]
            a, b = (0, PPM // 2) if s <= PPM // 2 else (PPM // 2, PPM)
            # Grid-point monotonicity from the true fixed-bank price function.
            known = min(bound[str(t)] for t in S["SCALES"] if t <= s)
            interp = ((b - s) * bound[str(a)] + (s - a) * bound[str(b)]) // (b - a)
            vals.append(min(known, interp + v["possible_callbacks"]))
        return min(vals)

    cut = S["threshold"](upper)
    return {
        "max_not_excluded_ppm": cut["max_feasible_ppm"],
        "first_certified_no_go_ppm": cut["first_infeasible_ppm"],
    }


def run(a):
    check(
        digest(HERE / "dual-protocol.md") == PROTO and digest(HERE / "score.py") == SOURCE,
        "proof, pricing and certificate protocol",
    )
    old = S["Q"]["pinned"](a.previous, OLD)
    bank_lists = S["Q"]["pinned"](a.witnesses, S["WITNESSES"])
    if a.shares is not None:
        check(a.shares_sha256 is not None, "expected certificate identity")
        import gzip

        payload = a.shares.read_bytes()
        if a.shares.suffix == ".gz":
            payload = gzip.decompress(payload)
        check(hashlib.sha256(payload).hexdigest() == a.shares_sha256, "canonical private shares")
        supplied = json.loads(payload)
    else:
        check(
            a.shares_sha256 is None
            and digest(Path("/usr/bin/lp_solve")) == LP_SHA
            and digest(Path("/lib64/liblpsolve55.so")) == LIB_SHA,
            "local solver identity",
        )
        supplied = None
    populations, offered, _ = S["get_populations"](a.archive)
    r = {
        "status": "INTEGER_VERIFIED_K353_CAPACITY_CERTIFICATES",
        "previous_sha256": OLD,
        "protocol_sha256": PROTO,
        "source_sha256": digest(Path(__file__)),
        "solver_for_proposals_only": {"exe_sha256": LP_SHA, "library_sha256": LIB_SHA},
        "regimes": {},
    }
    proofs = {}
    for mode, ordered in sorted(bank_lists.items()):
        bank = set(map(tuple, ordered))
        check(len(bank) == CAP and bank <= offered, "fixed witness")
        clocks = {}
        for label in CLOCKS:
            tag, phase = label.split(".")
            keep = S["PHASES"][:2] if phase == "first" else S["PHASES"][1:]
            events = [e for e in populations[tag][mode] if e.phase in keep]
            v = old["regimes"][mode]["clocks"][label]
            baseline = v["before_bank_margin_ns"]
            c = {"possible_callbacks": len(events), "upper_ns": {}, "witness_margin_ns": {}}
            for scale in S["SCALES"]:
                k = f"{mode}/{label}/{scale}"
                s = str(scale)
                known = v["scales_ppm"][s]
                u, proof = evaluate(
                    events, offered, bank, scale, CAP, supplied[k] if supplied is not None else None
                )
                proofs[k] = proof
                c["upper_ns"][s] = min(known["any_upper_margin_ns"], u + baseline)
                c["witness_margin_ns"][s] = known["fixed_margin_ns"]
                check(c["upper_ns"][s] >= known["fixed_margin_ns"], "upper vs measured witness")
            for j, s in enumerate(S["SCALES"]):
                c["upper_ns"][str(s)] = min(c["upper_ns"][str(t)] for t in S["SCALES"][: j + 1])
            clocks[label] = c
        r["regimes"][mode] = {"clocks": clocks, "necessary": frontier(clocks)}
    check(supplied is None or supplied == proofs, "extra proofs")
    buffer = serialize(proofs)
    r["canonical_shares_sha256"] = hashlib.sha256(buffer).hexdigest()
    (a.new_output_dir / "shares.json").write_bytes(buffer)
    return r


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "previous", "witnesses", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--shares", type=Path)
    p.add_argument("--shares-sha256")
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(args)
    except Exception as exc:
        report = {"status": "FAIL_PRESERVED", "reason": str(exc), "error": type(exc).__name__}
    (args.new_output_dir / "receipt.json").write_bytes(serialize(report))
    print(report["status"])
    raise SystemExit(int(report["status"] == "FAIL_PRESERVED"))
