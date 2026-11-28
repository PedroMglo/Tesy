"""Price the actual serial cold groups against the physical hot-forward frontier."""

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
WAVE = HERE.parent / "layer/prefix/wave"
T = run_path(WAVE / "tier_bank.py")
need = T["need"]
E = HERE / "evidence-20261128-r01"
PATHS = dict(
    service=WAVE / "evidence-20261128-r01/service.json.gz",
    transactions=WAVE / "evidence-tier-20261128-r01/transactions.json.gz",
    bank=WAVE / "evidence-tier-20261128-r01/receipt.json",
    resident=E / "resident.json",
    barriers=E / "barriers.json",
)
ALIGNED = 13221888
PPM = 1_000_000


def load(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def groups(journal, tx, effects, physical, actual):
    hits = {}
    for (call, tile, layer, _, _, expert, _), (_, source, _) in zip(tx, effects, strict=True):
        key = (call, tile, layer, expert)
        need(key not in hits, "repeated key within site")
        hits[key] = source is not None
    modes = {"primary": [], "secondary": []}
    keys = set()
    demand = Counter()
    by_call = Counter()
    sites = set()
    for call, tile, layer, *_, work in journal["groups"]:
        if call <= 2:
            continue
        at = call - 2
        need(
            1 <= at <= 46 and 0 <= layer < 36 and (at, layer) not in sites and len(work) <= 4,
            "one top-4 remap per layer",
        )
        sites.add((at, layer))
        if actual:
            true = actual["decode"][at - 1]["routes"][layer]
            need(
                all(expert in true for expert, _, _ in work), "historical miss outside target route"
            )
        if not work:
            continue
        by_call[at] += len(work)
        jobs = []
        for expert, rd, st in work:
            key = (call, tile, layer, expert)
            need(key in hits and key not in keys and rd > 0 and st > 0, "price or reservation")
            keys.add(key)
            hit = hits[key]
            jobs.append((rd, st, hit))
            demand.update(
                jobs=1, early=int(at <= 44), hits=int(hit), early_hits=int(hit and at <= 44)
            )
        modes["secondary"].append((at, jobs))
        modes["primary"].append((at, [(rd, st, False) for rd, st, _ in jobs]))
    # The sealed time table stores only layers that reserved a generation.
    # An omitted layer contributes zero service iff the complete ledger has no
    # reservation at that site. S independently executed 36 remaps each time.
    expected_sites = {(call - 2, layer) for call, _, layer, _ in hits if call > 2}
    need(
        keys == {k for k in hits if k[0] > 2}
        and sites == expected_sites
        and all(r["counts"][0] == 36 for r in physical["decode"])
        and [by_call[at] for at in range(1, 47)] == [r["counts"][2] for r in physical["decode"]],
        "all single-token loads",
    )
    return modes, dict(demand, nonempty_layers=len(sites), resident_only_layers=46 * 36 - len(sites))


def price_group(jobs, rate, ppm):
    # Each job owns a reader through READ and its three ordered SETs.
    longest = max(st if hit else st + (rd * ppm + PPM - 1) // PPM for rd, st, hit in jobs)
    size = sum(not hit for _, _, hit in jobs) * ALIGNED
    device = (size * 10**9 + rate - 1) // rate
    return max(longest, device)


def largest_scale(score):
    if score(0) < 0:
        return None
    if score(PPM) >= 0:
        return PPM
    lo, hi = 0, PPM
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if score(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return lo


def mode(rows, rate, frontier):
    @cache
    def cost(ppm):
        dur = [(at, price_group(jobs, rate, ppm)) for at, jobs in rows]
        return sum(n for at, n in dur if at <= 44), sum(n for _, n in dur)

    first, decode = cost(PPM)
    arms = []
    for w in frontier:
        ff = w["all_hot_first_range_ns"]
        d = w["all_hot_decode_ns"]
        max_decode = 47 * 10**9 // 6 - d

        def scale(deadline, max_decode=max_decode):
            def slack(ppm):
                ef, ed = cost(ppm)
                return min(deadline - ef, max_decode - ed)

            return largest_scale(slack)

        arms.append(
            dict(
                W=w["W"],
                repeat=w["repeat"],
                first_ns=[v + first for v in ff],
                decode_ns=d + decode,
                common_extra_ns=min(10**10 - ff[1] - first, max_decode - decode),
                max_read_ppm=[scale(10**10 - v) for v in ff],
            )
        )
    any_fit = any(v["first_ns"][0] <= 10**10 and v["decode_ns"] <= 47 * 10**9 // 6 for v in arms)
    all_fit = all(v["common_extra_ns"] >= 0 for v in arms)
    return dict(
        decision="GO_FIXTURE_ONLY"
        if all_fit
        else "INCONCLUSIVE"
        if any_fit
        else "NO_GO_FIXED_SERVICE",
        original_service_ns=cost(PPM),
        zero_read_price_physical_volume_ns=cost(0),
        arms=arms,
    )


def run(actual_path):
    p = {k: load(path) for k, path in PATHS.items()}
    job = p["transactions"]
    freq = Counter({(layer, expert): n for layer, expert, n in job["counts"]})
    caps = T["quotas"](freq)
    effects, bank = T["run_order"](
        job["reservations"], job["initial"], [tuple(k) for k in job["seed"]], freq, caps, True
    )
    existing = p["bank"]["result"]
    need(
        caps == existing["caps"] and bank["hits"] == existing["partition"]["hits"],
        "frozen secondary policy",
    )
    control = p["barriers"]["evidence"]["S"]
    native_hash = next(
        r["native_sha256"] for r in p["barriers"]["provenance"]["arms"] if r["role"] == "S"
    )
    actual = load(actual_path) if actual_path else None
    if actual:
        need(sha(actual_path) == native_hash and actual["role"] == "S", "native S")
    arms = {}
    for tag, data in p["service"]["journals"].items():
        modes, counts = groups(data, job["reservations"], effects, control, actual)
        selected = [
            v
            for v in p["resident"]["prices"]
            if v["role"] == "S" and v["replay"] == 1 and v["prefill"] == tag
        ]
        need(len(selected) == 4, "two independent W and two repeats")
        arms[tag] = dict(
            counts=counts,
            prices={
                name: {str(rate): mode(rows, rate, selected) for rate in (4500000000, 8000000000)}
                for name, rows in modes.items()
            },
        )
    return dict(
        inputs={k: sha(v) for k, v in PATHS.items()},
        protocol_sha256=sha(HERE / "service-protocol.md"),
        program_sha256=sha(Path(__file__)),
        serial_native_sha256=native_hash,
        caps=caps,
        arms=arms,
        model_forwards=0,
        evidence="TRACE_DERIVED_CONDITIONAL_BLOCKING",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial-native", type=Path)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    need(
        a.check or a.serial_native, "verify expert membership in the physical S before publication"
    )
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        receipt = json.loads(json.dumps(run(a.serial_native)))
        if a.check:
            need(receipt == load(a.check), "blocking service prices differ")
        else:
            with (a.new_output_dir / "receipt.json").open("x") as out:
                json.dump(receipt, out, sort_keys=True, separators=(",", ":"))
                out.write("\n")
        print(
            {
                k: v["prices"]["secondary"]["4500000000"]["decision"]
                for k, v in receipt["arms"].items()
            }
        )
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc)))
            )
        raise
