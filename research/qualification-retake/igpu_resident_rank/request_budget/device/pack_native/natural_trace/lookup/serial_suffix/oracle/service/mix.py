"""Check that per-remap convex mixtures certify a bound simultaneously for every bank."""

import argparse
import gzip
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(str(HERE / "dual.py"))
S, MIX = D["S"], 1_000_000
check, digest, serialize = D["check"], D["digest"], D["serialize"]
METHOD = "07b4efd7c66242d628fec750d2d35cc890c1dcbec23c40eb7c22008c7f86c6e9"
PRIOR = "c1c659c30dceec10139f8f2ca2f0d9cd15a6d722cd762f3a88e88f9245a8ed3c"


def options(events, offered, bank, scale):
    """Identical support vectors can be represented by the first one in the sealed order."""
    result = []
    for e in events:
        unique = []
        for mode in D["SUPPORTS"]:
            row = dict(D["weighted"]([e], offered, bank, scale, mode))
            if row not in unique:
                unique.append(row)
        result.append(unique)
    return result


def weights(choices, mix):
    check(len(choices) == len(mix), "wave count")
    totals = Counter()
    for opts, fractions in zip(choices, mix, strict=True):
        check(
            len(fractions) == len(opts)
            and all(type(v) is int and v >= 0 for v in fractions)
            and sum(fractions) == MIX,
            "non-convex support",
        )
        for opt, f in zip(opts, fractions, strict=True):
            for key, v in opt.items():
                totals[key] += f * v
    return sorted(totals.items())


def program(choices, cap):
    """LP in milliseconds. Only proposals for mix and share variables are read back."""
    base = Counter()
    delta = defaultdict(dict)
    constraints = []
    for i, opts in enumerate(choices):
        base.update(opts[0])
        if len(opts) > 1:
            constraints.append(" + ".join(f"t{i}c{a}" for a in range(1, len(opts))) + " <= 1;")
        for a, opt in enumerate(opts[1:], start=1):
            for keys in opt.keys() | opts[0].keys():
                v = opt.get(keys, 0) - opts[0].get(keys, 0)
                if v:
                    delta[keys][f"t{i}c{a}"] = v
    keysets = sorted(base.keys() | delta.keys())
    members = defaultdict(list)
    obj = Counter()
    objectives = [f"{cap} lim"]
    for j, keys in enumerate(keysets):
        if len(keys) == 1:
            continue
        objectives.append(f"- d{j}")
        obj.update(delta[keys])
        for k in keys:
            members[k].append(f"+ d{j}")
        lhs = f"d{j} " + terms(delta[keys], -1)
        constraints.append(f"{lhs} <= {base[keys] / MIX:.6f};")
    for j, k in enumerate(sorted({k for keys in keysets for k in keys})):
        objectives.append(f"+ v{j}")
        row = " ".join(members[k]) + " " + terms(delta[(k,)], 1) + f" - lim - v{j}"
        constraints.append(f"{row} <= {-base[(k,)] / MIX:.6f};")
    return "\n".join(["min: " + " ".join(objectives) + " " + terms(obj, 1) + ";", *constraints])


def terms(coeffs, sign):
    return " ".join(
        f"{'+' if sign * v > 0 else '-'} {abs(v) / MIX:.6f} {k}"
        for k, v in sorted(coeffs.items())
        if v
    )


def propose(choices, cap):
    if all(len(opts) == 1 for opts in choices):
        mix = [[MIX] for _ in choices]
        w = weights(choices, mix)
        d = D["propose"]([(k, v // MIX) for k, v in w], cap)
        return {"mix": mix, "shares": [v * MIX for v in d]}
    result = subprocess.run(
        ["/usr/bin/lp_solve", "-S2"],
        input=program(choices, cap) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
        env={"LC_ALL": "C"},
    )
    suggestions = {}
    for line in result.stdout.splitlines():
        pair = line.split()
        if len(pair) == 2 and pair[0][0] in "td" and pair[0][1:2].isdigit():
            check(pair[0] not in suggestions, "duplicate LP variable")
            suggestions[pair[0]] = Decimal(pair[1])
    mix = []
    for i, opts in enumerate(choices):
        remain = MIX
        relevant = []
        for a in range(1, len(opts)):
            mass = min(remain, max(0, int(suggestions[f"t{i}c{a}"] * MIX)))
            relevant.append(mass)
            remain -= mass
        mix.append([remain, *relevant])
    shares = []
    for j, (keys, v) in enumerate(weights(choices, mix)):
        proposed = v if len(keys) == 1 else round(suggestions[f"d{j}"] * MIX * MIX)
        shares.append(min(v, max(0, proposed)))
    return {"mix": mix, "shares": shares}


def certify(choices, proof, cap):
    w = weights(choices, proof["mix"])
    return D["verify"](w, proof["shares"], cap) // MIX


def run(a):
    check(digest(HERE / "per-wave-protocol.md") == METHOD, "prospective scope")
    prior = S["Q"]["pinned"](a.previous_dual, PRIOR)
    old = S["Q"]["pinned"](a.previous, D["OLD"])
    witness = S["Q"]["pinned"](a.witnesses, S["WITNESSES"])
    check(
        prior["previous_sha256"] == D["OLD"]
        and digest(HERE / "dual.py") == prior["source_sha256"]
        and digest(HERE / "score.py") == D["SOURCE"],
        "pricing and dual chain",
    )
    supplied = None
    if a.shares is None:
        check(
            not a.shares_sha256
            and digest(Path("/usr/bin/lp_solve")) == D["LP_SHA"]
            and digest(Path("/lib64/liblpsolve55.so")) == D["LIB_SHA"],
            "solver identity",
        )
    else:
        payload = a.shares.read_bytes()
        if a.shares.suffix == ".gz":
            payload = gzip.decompress(payload)
        check(hashlib.sha256(payload).hexdigest() == a.shares_sha256, "canonical partitions")
        supplied = json.loads(payload)
    pop, offered, _ = S["get_populations"](a.archive)
    ev = [e for e in pop["P106"]["split"] if e.phase != "decode_tail"]
    bank = set(map(tuple, witness["split"]))
    c = prior["regimes"]["split"]["clocks"]
    row = c["P106.first"]
    previous = row["upper_ns"].copy()
    baseline = old["regimes"]["split"]["clocks"]["P106.first"]["before_bank_margin_ns"]
    check(
        len(ev) == row["possible_callbacks"] and len(bank) == S["CAP"] and bank <= offered,
        "P106 first-final population and sealed witness",
    )
    proofs = {}
    for scale in S["SCALES"]:
        k = str(scale)
        choices = options(ev, offered, bank, scale)
        proof = supplied[k] if supplied is not None else propose(choices, S["CAP"])
        upper = baseline + certify(choices, proof, S["CAP"])
        check(row["witness_margin_ns"][k] <= upper, "witness must be below certificate")
        row["upper_ns"][k] = min(previous[k], upper)
        proofs[k] = proof
    check(supplied is None or proofs == supplied, "extra proof rows")
    for i, scale in enumerate(S["SCALES"]):
        row["upper_ns"][str(scale)] = min(row["upper_ns"][str(s)] for s in S["SCALES"][: i + 1])
    data = serialize(proofs)
    (a.new_output_dir / "shares.json").write_bytes(data)
    return {
        "status": "VERIFIED_K353_PER_WAVE_CAPACITY_CERTIFICATE",
        "protocol_sha256": METHOD,
        "source_sha256": digest(Path(__file__)),
        "previous_dual_sha256": PRIOR,
        "scope": "split/P106.first",
        "previous_upper_ns": previous,
        "result": row,
        "joint_necessary": D["frontier"](c),
        "canonical_shares_sha256": hashlib.sha256(data).hexdigest(),
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "previous", "previous-dual", "witnesses", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--shares", type=Path)
    cli.add_argument("--shares-sha256")
    args = cli.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(args)
    except Exception as exc:
        report = {"status": "FAIL_PRESERVED", "reason": str(exc), "error": type(exc).__name__}
    (args.new_output_dir / "receipt.json").write_bytes(serialize(report))
    print(report["status"])
    raise SystemExit(int(report["status"] == "FAIL_PRESERVED"))
