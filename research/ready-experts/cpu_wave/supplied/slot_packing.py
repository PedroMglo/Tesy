"""Certify non-preemptive four-worker lower bounds on the sealed joint intervention."""

import argparse
import gzip
import json
import os
import subprocess
from bisect import insort
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(HERE / "slot_bank.py")
L, need, sha, limits = (B[k] for k in ("LIFE", "need", "sha", "limits"))
METHOD = "b74fa24e9fd2c4f647bb19c5b19e7a76e49d5166ebc8aa4a53d6f237b670fd2d"
PARENT = "539a1e730336fed3d8fa52d35d3149357c495b2776107e87cf50acac1456fc4e"


def greedy(costs):
    loads = [0] * 4
    for cost in costs:
        i = loads.index(min(loads))
        loads[i] += cost
    return max(loads)


@lru_cache(maxsize=8192)
def exact_four(costs):
    """Minimum makespan, enumerating assignments of this descending list of at most 12 jobs."""
    low = max(costs[0], (sum(costs) + 3) // 4)
    best = greedy(costs)
    loads = [0] * 4

    def search(i):
        nonlocal best
        if best == low:
            return
        if i == len(costs):
            best = min(best, max(loads))
            return
        tried = set()
        for lane in sorted(range(4), key=loads.__getitem__):
            prior = loads[lane]
            if prior in tried or prior + costs[i] >= best:
                continue
            tried.add(prior)
            loads[lane] += costs[i]
            search(i + 1)
            loads[lane] = prior

    search(0)
    return best


@lru_cache(maxsize=2048)
def fits_in_four(costs, cap):
    """Independent subset DP: fewest bins first, then lightest possible final bin."""
    if max(costs) > cap or sum(costs) > 4 * cap:
        return False
    dp = [(0, 0)] * (1 << len(costs))
    dp[0] = (1, 0)
    for mask in range(1, len(dp)):
        best = (len(costs) + 1, 0)
        bits = mask
        while bits:
            bit = bits & -bits
            bins, last = dp[mask ^ bit]
            weight = costs[bit.bit_length() - 1]
            trial = (bins, last + weight) if last + weight <= cap else (bins + 1, weight)
            best = min(best, trial)
            bits ^= bit
        dp[mask] = best
    return dp[-1][0] <= 4


def path_floor(jobs, entry, gaps):
    # Each graph transition and each service interval points strictly forward in wave time.
    deadlines = defaultdict(list)
    starts = set()
    for j in jobs:
        read = max(2 * j.horizon, 2 * j.old_use + 1 if j.cpu else 0)
        put = 2 * j.reserve
        deadlines[2 * j.due + 1].append((read, put, j.read, j.put))
        starts.update((read, put))
    ordered = sorted(deadlines.items())
    end = 2 * len(gaps)
    weak, strong = [0] * (end + 1), [0] * (end + 1)
    parent = [None] * (end + 1)
    for a in range(end):
        gap = (entry if a == 0 else 0) if a % 2 == 0 else gaps[a // 2]
        weak[a + 1] = max(weak[a + 1], weak[a] + gap)
        if parent[a + 1] is None or strong[a] + gap >= strong[a + 1]:
            strong[a + 1] = strong[a] + gap
            parent[a + 1] = (a, a + 1, "graph", gap)
        if a not in starts:
            continue
        total = count = 0
        top = []
        for b, batch in ordered:
            added = 0
            for r, p, rr, pp in batch:
                cost = (rr if r >= a else 0) + (pp if p >= a else 0)
                if cost:
                    insort(top, cost)
                    if len(top) > 12:
                        top.pop(0)
                    total += cost
                    count += 1
                    added += 1
            if not added:
                continue
            need(b > a, "service interval points backward")
            base = max(top[-1], (total + 3) // 4)
            weak[b] = max(weak[b], weak[a] + base)
            weights = tuple(reversed(top))
            price = base
            if count > 4 and greedy(weights) > base:
                price = max(price, exact_four(weights))
            if strong[a] + price > strong[b]:
                strong[b] = strong[a] + price
                parent[b] = a, b, "service", price, total, count, weights
    chain = []
    cursor = end
    while cursor:
        step = parent[cursor]
        chain.append(step)
        cursor = step[0]
    compact = []
    for step in reversed(chain):
        if compact and compact[-1][2] == step[2] == "graph":
            left, _, kind, value = compact.pop()
            compact.append((left, step[1], kind, value + step[3]))
        else:
            compact.append(step)
    need(strong[-1] >= weak[-1] and sum(e[3] for e in compact) == strong[-1], "path accounting")
    return weak[-1], strong[-1], compact


def verify_call(waves, chain):
    cursor = elapsed = improved = 0
    for a, b, kind, price, *evidence in chain:
        need(cursor == a < b <= 2 * waves and price >= 0, "certificate endpoints")
        if kind == "service":
            total, count, top = evidence
            weights = tuple(top)
            need(
                0 < len(weights) == min(count, 12)
                and min(weights) > 0
                and list(weights) == sorted(weights, reverse=True)
                and sum(weights) <= total,
                "invalid interval accounting",
            )
            base = max(weights[0], (total + 3) // 4)
            need(price >= base, "invalid base price")
            if price > base:
                need(
                    not fits_in_four(weights, price - 1) and fits_in_four(weights, price),
                    "finite jobs fit into the claimed impossible interval",
                )
                improved += 1
        else:
            need(kind == "graph" and not evidence, "unknown certificate step")
        cursor = b
        elapsed += price
    need(cursor == 2 * waves, "incomplete call path")
    return elapsed, improved


def verify(proof, result):
    need(set(proof["traces"]) == set(result["traces"]) == {"P97", "P106"}, "two complete journals")
    need(
        proof["protocol_sha256"] == result["protocol_sha256"] == METHOD
        and proof["parent_sha256"] == result["parent_sha256"] == PARENT,
        "proof lineage",
    )
    for label, row in proof["traces"].items():
        need(
            row["journal_sha256"] == result["traces"][label]["journal_sha256"]
            and len(row["calls"]) == 48,
            "journal or call count",
        )
        clock, improved = row["exterior_ns"].copy(), 0
        for n, (number, waves, chain) in enumerate(row["calls"], 1):
            need(n == number, "call order")
            total, tests = verify_call(waves, chain)
            improved += tests
            L["add_time"](clock, n, total)
        need(
            clock == result["traces"][label]["floor_ns"]
            and improved == result["traces"][label]["partition_edges_in_witness"],
            "client clock, decode window or certificate count",
        )


def run(archive, renewal, out):
    src_root = HERE.parents[1]
    screen = run_path(src_root / "screen.py")
    src = screen["SOURCE"]
    primary = run_path(src_root / "primary/replay.py")
    iv, co = primary["IV"], primary["CO"]
    parent = src["pinned"](HERE / "slot-bank.json", PARENT)
    need(
        sha(HERE / "slot-packing.md") == METHOD
        and sha(HERE / "slot_bank.py") == parent["source_sha256"],
        "protocol or parent program seal",
    )
    lineage = src["pinned"](HERE / "slot-lifetime.json", parent["parent_sha256"])
    need(sha(HERE / "slot_lifetime.py") == lineage["source_sha256"], "parent lifetime source")
    bank_ref = src["pinned"](renewal / "intervals/receipt.json", parent["bank_sha256"])
    bank_path = renewal / "intervals/schedule.json.gz"
    need(sha(bank_path) == parent["bank_proof_sha256"], "bank schedule seal")
    saved = json.loads(gzip.decompress(bank_path.read_bytes()))["frequency"]
    placed = co["placements"](renewal / "placement")
    grants = src["pinned"](co["LOOKUP"] / "empty-result.json", co["EMPTY_RESULT"])
    prior = src["pinned"](
        screen["NATURAL"] / "prefill_retention/request_cost/receipt.json", screen["PRIOR"]
    )
    root = archive / "part-106" / src["SOURCES"]["P106"][0]
    counts, cut = iv["train"](root / "ON")
    banks, rows106, _, _ = src["Q"]["read_new"](root, src["SOURCES"]["P106"][1])
    seed = list(map(tuple, banks["banks"]["lru"]["ordered_keys"]))
    need(cut == parent["t1_prefix_sha256"], "bank training boundary")
    results, proof = {}, dict(protocol_sha256=METHOD, parent_sha256=PARENT, traces={})
    for label in ("P97", "P106"):
        rows = rows106
        if label == "P97":
            path = archive / "part-97" / src["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = src["T"]["PFJ"]["read_journal"](path)
        (_, ext), tx, initial, _, _, seals = iv["load_arm"](
            archive, label, rows, seed, prior[label]
        )
        need(list(seals) == bank_ref["routing_and_reservations"], "different bank transactions")
        hits = B["bank"](iv, bank_ref, tx, initial, seed, counts, saved)
        calls, _, _ = L["ledger"](rows, src, primary)
        graph, _ = B["graph_cases"](rows, src, co, placed, grants["journals"][label])
        original = parent["traces"][label]["regimes"]["frequency"]["two_oracle"]["empty_wave_grant"]
        base, floor, shown, edges = ext.copy(), ext.copy(), [], 0
        for n, jobs in calls.items():
            need(all(tx[j.order].generation == j.key for j in jobs), "bank job key")
            priced = B["intervention"](jobs, {}, hits, None, "two_oracle", 100)
            entry, alternatives = graph[n]
            gaps = alternatives["empty_wave_grant"]
            relaxed, stronger, chain = path_floor(priced, entry, gaps)
            duration, tests = verify_call(len(gaps), chain)
            need(duration == stronger, "independent arithmetic")
            L["add_time"](base, n, relaxed)
            L["add_time"](floor, n, stronger)
            shown.append((n, len(gaps), chain))
            edges += tests
        need(
            base == original["floor"]
            and all(base[k] <= floor[k] <= original["schedule"][k] for k in limits),
            "original floor or feasible bound",
        )
        seal = parent["traces"][label]["journal_sha256"]
        proof["traces"][label] = dict(journal_sha256=seal, exterior_ns=ext, calls=shown)
        results[label] = dict(
            floor_ns=floor,
            original_floor_ns=base,
            schedule_ns=original["schedule"],
            partition_edges_in_witness=edges,
            journal_sha256=seal,
            decision=L["decision"](floor, original["schedule"]),
        )
    file = out / "packing-paths.json.gz"
    data = json.dumps(proof, separators=(",", ":")).encode() + b"\n"
    with file.open("xb") as f:
        f.write(gzip.compress(data, compresslevel=9, mtime=0))
    result = dict(
        classification="CONDITIONAL_INTEGER_CERTIFICATE",
        traces=results,
        protocol_sha256=METHOD,
        source_sha256=sha(Path(__file__)),
        parent_sha256=PARENT,
        certificate_sha256=sha(file),
        model_forwards=0,
        gpu_forwards=0,
    )
    verify(json.loads(gzip.decompress(file.read_bytes())), result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--certificate", type=Path)
    p.add_argument("--receipt", type=Path)
    for opt in ("archive", "renewal", "new-output-dir"):
        p.add_argument("--" + opt, type=Path)
    args = p.parse_args()
    if args.certificate:
        r = json.loads(args.receipt.read_bytes())
        need(
            sha(args.certificate) == r["certificate_sha256"]
            and sha(Path(__file__)) == r["source_sha256"],
            "certificate/program digest",
        )
        verify(json.loads(gzip.decompress(args.certificate.read_bytes())), r)
        print("PASS four-worker path arithmetic")
    else:
        need(
            args.archive and args.renewal and args.new_output_dir,
            "archive, renewal and new output required",
        )
        os.umask(0o077)
        args.new_output_dir.mkdir()
        try:
            git = ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
            refs = subprocess.check_output(
                [*git, "rev-parse", "HEAD", "HEAD^{tree}"], cwd=HERE, text=True
            ).splitlines()
            prov = dict(
                commit=refs[0],
                tree=refs[1],
                protocol_sha256=METHOD,
                source_sha256=sha(Path(__file__)),
            )
            (args.new_output_dir / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
            need(
                not subprocess.check_output([*git, "status", "--porcelain"], cwd=HERE),
                "unclean campaign",
            )
            r = run(args.archive, args.renewal, args.new_output_dir)
        except Exception as exc:
            missing = (
                isinstance(exc, FileNotFoundError)
                and exc.filename
                and any(
                    Path(exc.filename).resolve().is_relative_to(root.resolve())
                    for root in (args.archive, args.renewal)
                )
            )
            r = dict(
                classification="NOT_RUN_RAW_REQUIRED" if missing else "FAIL_PRESERVED",
                reason=str(exc),
            )
        temp = args.new_output_dir / ".receipt.tmp"
        with temp.open("x") as f:
            json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
            f.write("\n")
        temp.rename(args.new_output_dir / "slot-packing.json")
        print(r["classification"], r.get("reason", ""))
        raise SystemExit(r["classification"] != "CONDITIONAL_INTEGER_CERTIFICATE")
