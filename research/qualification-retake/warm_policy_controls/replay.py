"""Compare causal per-layer victim rules from a validated C294 decode boundary."""

import argparse
import hashlib
import json
import resource
import runpy
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cache_bound  # noqa: E402
import cache_boundary as boundary  # noqa: E402

EXPERT_BYTES = 13_219_200
ROUTE_RECEIPT = "17f162d75013e04c6f47f776b264c5b7b3e9801cf206ed531434c75a45773ef0"
OPTIMUM = "80b22417608677f3d7316396068a319ac199056e15cdd0cae4e7447bd627c059"
PROTOCOL = "7b0d0d27e25db45e23041e90b287a201ec1ed050d0b2f297a5b91245f75c06bb"


def replay(residents, groups, *, scores=None, decode_lru=False, capacity=40):
    """Return layer-local final ID sets and hit/miss/eviction counters, touching ordered ranks."""
    boundary.require(capacity >= 4 and not (scores is not None and decode_lru), "incompatible rule")
    pools = [set(pool) for pool in residents]
    boundary.require(
        all(
            len(pool) <= capacity and all(type(x) is int and 0 <= x < 128 for x in pool)
            for pool in pools
        ),
        "invalid initial pool",
    )
    if scores is None:
        ranking = [[0] * 128 for _ in pools]
    else:
        boundary.require(
            len(scores) == len(pools)
            and all(
                len(row) == 128 and all(type(x) is int and x >= 0 for x in row) for row in scores
            ),
            "invalid frequency table",
        )
        ranking = [list(row) for row in scores]

    counters = [dict(hits=0, misses=0, evictions=0) for _ in pools]
    clocks = [0] * len(pools)
    for _call, layer, _pos, ids in groups:
        pinned = set(ids)
        boundary.require(
            0 <= layer < len(pools)
            and len(ids) == len(pinned) == 4
            and all(type(x) is int and 0 <= x < 128 for x in ids),
            "invalid group",
        )
        pool, stats = pools[layer], counters[layer]
        for expert in ids:
            if expert in pool:
                stats["hits"] += 1
            else:
                stats["misses"] += 1
                if len(pool) == capacity:
                    victim = min(pool - pinned, key=lambda v: (ranking[layer][v], -v))
                    pool.remove(victim)
                    stats["evictions"] += 1
                pool.add(expert)
            if decode_lru:
                clocks[layer] += 1
                ranking[layer][expert] = clocks[layer]
        boundary.require(pinned <= pool, "pinned expert evicted")
    return pools, counters


def fixture():
    def one(ids):
        return [(1, 0, 0, ids)]

    # Expert 9 is the highest ID but is pinned by a later rank. 5 must leave instead.
    pools, counts = replay([{1, 5, 8, 9}], one([4, 1, 9, 8]), capacity=4)
    boundary.require(
        pools == [{1, 4, 8, 9}] and counts == [dict(hits=3, misses=1, evictions=1)],
        "late pin or tie",
    )
    inp = [{3, 4, 9}]
    groups = [(1, 0, 0, [9, 6, 4, 3]), (2, 0, 1, [3, 1, 4, 9]), (3, 0, 2, [3, 1, 2, 4])]
    a, ac = replay(inp, groups, capacity=5)
    b, bc = replay(inp, groups, decode_lru=True, capacity=5)
    # At the final step 6 and 9 are unpinned. Only 9 was touched in the previous group.
    boundary.require(
        a == [{1, 2, 3, 4, 6}]
        and b == [{1, 2, 3, 4, 9}]
        and ac == bc == [dict(hits=9, misses=3, evictions=1)]
        and inp == [{3, 4, 9}],
        "initial vacancies or recency refresh",
    )
    # Two no-history LRU candidates at time zero are broken by ID.
    a, _ = replay([{1, 3, 5, 7, 9}], one([1, 3, 4, 6]), decode_lru=True, capacity=5)
    boundary.require(a == [{1, 3, 4, 5, 6}], "LRU initial tie")
    ranking = [[0] * 128]
    ranking[0][9] = 2
    c, _ = replay(inp, groups, scores=ranking, capacity=5)
    boundary.require(c == b, "fixed frequency priority")


def checked(path, digest):
    data = path.read_bytes()
    boundary.require(hashlib.sha256(data).hexdigest() == digest, "changed sealed input")
    return json.loads(data)


def audit(raw):
    reference = runpy.run_path(str(HERE.parent / "warm_route_reference/verify.py"))
    route = checked(HERE.parent / "warm_route_reference/evidence-r4/receipt.json", ROUTE_RECEIPT)
    optimum = checked(HERE.parent / "cache-paid-evidence/receipt.json", OPTIMUM)
    boundary.require(
        route["status"] == "PASS_HISTORICAL_ORDERED_DECODE", "unqualified route history"
    )
    arms = {}
    for name in boundary.NAMES:
        case = name.split("-")[1]
        pools, facts = boundary.audit_arm(raw, name)
        ref = route["arms"][name]
        hashes = facts["source_sha256"]
        boundary.require(
            all(digest == ref["source_sha256"][k] for k, digest in hashes.items()),
            "boundary / rank sources differ",
        )
        base = raw / (name + ".native")
        result = checked(base / "result.json", hashes["result.json"])
        path = base / "events.tsv"
        groups = reference["witness_rows"](path, case, hashes["events.tsv"])
        digest = reference["check_witness"](case, groups)
        boundary.require(digest == ref["ordered_decode_sha256"], "decode witness")
        actual = [0] * 36
        journal_hash = hashlib.sha256()
        with path.open("rb") as stream:
            journal_hash.update(next(stream))
            for line in stream:
                journal_hash.update(line)
                kind, _, call, _, layer, *_ = line.split()
                if kind == b"10" and int(call) >= 1:
                    actual[int(layer)] += 1
        boundary.require(
            journal_hash.hexdigest() == hashes["events.tsv"], "changed publication journal"
        )
        observed = sum(actual)
        bound = optimum["arms"][name + ".native"]
        boundary.require(
            observed == facts["counts"]["decode_publications"] == bound["observed_loads"],
            "unreconciled observed publications",
        )
        optimum_by_layer = [
            cache_bound.minimum(
                [set(row[3]) for row in groups if row[1] == layer], 40, set(pools[layer])
            )
            for layer in range(36)
        ]
        lower = sum(optimum_by_layer)
        boundary.require(lower == bound["minimum_uniform40"], "changed oracle")
        final = [
            {e for e, _, state, _ in pool if state == 2} for pool in boundary.slots(result["final"])
        ]
        layers = sorted(result["initial"]["layers"], key=lambda row: row["layer"])
        tiers = [r["native_cache_buffer"] for r in layers]
        boundary.require(
            set(tiers) == {"CPU", "CUDA0"}
            and all(r["logical_bytes_per_load"] == EXPERT_BYTES for r in layers),
            "unknown tier payload",
        )
        item = dict(
            ordered_decode_sha256=digest,
            boundary_slot_vector_sha256=facts["boundary_slot_vector_sha256"],
            source_sha256=hashes,
            observed_publications=observed,
            oracle_minimum=lower,
            R0_cuda_publications=sum(v for v, t in zip(actual, tiers, strict=True) if t == "CUDA0"),
            controls={},
        )
        for control in ("fixed_id", "decode_lru"):
            end, stats = replay(pools, groups, decode_lru=control == "decode_lru")
            total = {k: sum(row[k] for row in stats) for k in ("hits", "misses", "evictions")}
            boundary.require(
                total["hits"] + total["misses"] == 4608
                and all(s["misses"] >= m for s, m in zip(stats, optimum_by_layer, strict=True))
                and sum(map(len, end)) - sum(map(len, pools))
                == total["misses"] - total["evictions"],
                "cache conservation",
            )
            tier = {
                t: sum(s["misses"] for s, dev in zip(stats, tiers, strict=True) if dev == t)
                for t in set(tiers)
            }
            missing = [len(r - c) for r, c in zip(final, end, strict=True)]
            item["controls"][control] = {
                **total,
                "misses_by_tier": tier,
                "payload_bytes": total["misses"] * EXPERT_BYTES,
                "cuda_destination_payload_bytes": tier["CUDA0"] * EXPERT_BYTES,
                "oracle_gap": total["misses"] - lower,
                "saved_vs_observed": observed - total["misses"],
                "pass_10_percent": 10 * total["misses"] <= 9 * observed,
                "final_identity_sets_sha256": boundary.digest([sorted(s) for s in end]),
                "missing_R0_final_keys": sum(missing),
                "R0_final_identity_restore_payload_floor_bytes": sum(missing) * EXPERT_BYTES,
            }
        arms[name] = item
    decisions = {}
    for rule in ("fixed_id", "decode_lru"):
        cases = sum(
            all(arms[f"c294-{case}-{r}-on"]["controls"][rule]["pass_10_percent"] for r in (2, 3))
            for case in ("nominal153", "code153")
        )
        decisions[rule] = ("NO_GO", "INCONCLUSIVE", "GO_FIXTURE_ONLY")[cases]
    return arms, decisions


def main(raw, out):
    boundary.require(not out.resolve().is_relative_to(raw.resolve()), "output among raws")
    out.mkdir(exist_ok=False)
    start = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        protocol_sha256=PROTOCOL,
        ranking_anchor_receipt_sha256=ROUTE_RECEIPT,
        anchor_correction_sha256=hashlib.sha256((HERE / "anchor-r2.md").read_bytes()).hexdigest(),
        oracle_receipt_sha256=OPTIMUM,
        raw_manifest_sha256=boundary.MANIFEST_SHA,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        forwards=0,
        weight_bytes=0,
    )
    try:
        resource.setrlimit(resource.RLIMIT_AS, (256 * 2**20,) * 2)
        signal.signal(signal.SIGALRM, boundary.deadline)
        signal.alarm(60)
        boundary.require(
            hashlib.sha256((HERE / "protocol.md").read_bytes()).hexdigest() == PROTOCOL,
            "changed protocol",
        )
        fixture()
        r["arms"], r["decisions"] = audit(raw)
        r["status"] = "TRACE_DERIVED_FIXED_C294_DECODE"
    except FileNotFoundError:
        r["status"] = "NOT_RUN_RAW_REQUIRED"
    except (OSError, ValueError, KeyError, MemoryError) as exc:
        r["reason"] = type(exc).__name__ + ": " + str(exc)
    finally:
        signal.alarm(0)
    r.update(
        elapsed_s=round(time.monotonic() - start, 4),
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    if r["peak_rss_kib"] > 256 * 1024 or r["elapsed_s"] > 60:
        r["status"] = "FAIL_BUDGET"
    target = out / ".pending"
    with target.open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2)
        f.write("\n")
    target.rename(out / "receipt.json")
    return r["status"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    args = p.parse_args()
    sys.exit(
        0 if main(args.raw_dir, args.new_output_dir) == "TRACE_DERIVED_FIXED_C294_DECODE" else 1
    )
