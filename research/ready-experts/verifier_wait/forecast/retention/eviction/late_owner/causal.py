"""Decide a finite immutable source at drained target returns using past reads only."""

import argparse
import gzip
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
READY = HERE.parents[4]
OBS = run_path(HERE / "observe.py")
DL = run_path(READY / "renewal/deadlines.py")
TRAIN = run_path(READY / "selection.py")
CO, IV, B, CC, SRC, need = (DL[k] for k in ("CO", "IV", "B", "CC", "SRC", "need"))
save, sha, stride = (OBS[k] for k in ("save", "sha", "WINDOW"))
METHOD = "50b9184dbf4f8683f5cef456232aadf68370c8d4488104e7b71cbba411cc13d3"
CONTROL = "314db3ad9f772e3e1d8d564259cbcccc29d93c79123d5f6cf41f47b4e3a8970d"


def phase(call):
    if call == 1:
        return "5"
    if call == 2:
        return "148"
    return "decode_to_first_content" if call <= 46 else "tail"


def projection(rows):
    # No timing, route from a later token or physical address reaches the cache policy.
    events = []
    for r in rows:
        if r.kind == 1:
            events.append([1, r.call])
        elif r.kind == 2:
            events.append([2, int(r.b == r.c == 0)])
        elif r.kind in (11, 17):
            need(0 <= r.layer < 36 and 0 <= r.expert < 128, "expert identity")
            events.append([r.kind, 128 * r.layer + r.expert])
    return events


class Bank:
    def __init__(self, cap, frequency):
        self.cap = cap
        self.frequency = frequency
        self.seen = Counter()
        self.last = {}
        self.sequence = 0
        self.elected = set()
        self.ready = set()

    def replay(self, events, training=False):
        initial = len(self.ready)
        waiting = {}
        account = defaultdict(Counter)
        hits = set()
        call = count = 0
        opened = False
        for op, v in events:
            if op == 1:
                need(not opened and v == call + 1, "call order")
                call = v
                opened = True
            bucket = "T1_prefill" if call <= 9 else "T1_decode"
            a = account[bucket if training else phase(call)]
            if op == 11:
                need(opened and v not in waiting and 0 <= v < 36 * 128, "concurrent primary")
                hit = v in self.ready
                capture = v in self.elected and not hit
                count += 1
                self.sequence += 1
                self.seen[v] += 1
                self.last[v] = self.sequence
                a.update(jobs=1, hits=int(hit), disk=int(not hit), captures=int(capture))
                if hit:
                    hits.add(count)
                waiting[v] = capture
            elif op == 17:
                need(v in waiting, "publication without reservation")
                if waiting.pop(v):
                    need(v in self.elected and v not in self.ready, "stale or duplicate fill")
                    self.ready.add(v)
            elif op == 2:
                need(opened and v in (0, 1), "return order")
                opened = False
                a["returns"] += 1
                if v and not waiting:
                    a["drains"] += 1
                    winners = set(sorted(self.last, key=self.priority, reverse=True)[: self.cap])
                    a["evictions"] += len(self.ready - winners)
                    self.ready &= winners
                    self.elected = winners
            elif op != 1:
                raise ValueError("unknown cache event")
            need(self.ready <= self.elected and len(self.elected) <= self.cap, "capacity")
            a["peak_ready"] = max(a["peak_ready"], len(self.ready))
            a["peak_windows"] = max(a["peak_windows"], len(self.elected))
        need(not waiting and not opened, "terminal drain")
        need(sum(a["hits"] + a["disk"] for a in account.values()) == count, "read conservation")
        net_filled = sum(a["captures"] - a["evictions"] for a in account.values())
        need(len(self.ready) == initial + net_filled, "source ownership conservation")
        for a in account.values():
            a["pack_requested_B"] = a["disk"] * stride
            a["avoided_pack_B"] = a["hits"] * stride
        return hits, dict(account)

    def priority(self, key):
        return self.seen[key] if self.frequency else 0, self.last[key], key


def train_prefix(arm):
    profile = TRAIN["PROFILE"]
    seal = SRC["pinned"](arm / "before-t2.json", TRAIN["T1_SEAL"])

    def rows():
        return profile["iter_rows"](arm / "observer/events.pfj", 0, seal["records"])

    proof, _ = profile["prefix_grade"](rows(), profile["T1"], 9)
    need(all(v == seal[k] for k, v in proof.items()) and seal["records"] == 87736, "prefix seal")
    return projection(rows()), proof["sha256"]


def compact_regions(regs, discounted):
    result = []
    for (num, regions, edges), (n, new, after) in zip(regs, discounted, strict=True):
        need(n == num, "graph discount order")
        groups = []
        for reg, cut in zip(regions, new, strict=True):
            need(reg.site == cut.site and reg.jobs == cut.jobs, "discount changed a dependency")
            groups.append(
                [reg.internal, cut.internal, [[j.expert, j.read_ns, j.set_ns] for j in reg.jobs]]
            )
        result.append([num, groups, edges, after])
    return result


def obtain(archive, placement):
    arm = archive / "part-106" / SRC["SOURCES"]["P106"][0]
    t1, prefix = train_prefix(arm / "ON")
    sealed, observed, _, _ = SRC["Q"]["read_new"](arm, SRC["SOURCES"]["P106"][1])
    seed = list(map(tuple, sealed["banks"]["lru"]["ordered_keys"]))
    ref = SRC["pinned"](READY / "renewal/evidence/decision.json", CONTROL)
    journals = SRC["pinned"](OBS["EVIDENCE"] / "publications.json", OBS["PRIOR"])["sources"]
    previous = SRC["pinned"](
        B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"]
    )
    gaps = SRC["pinned"](CO["LOOKUP"] / "empty-result.json", CO["EMPTY_RESULT"])
    local = CO["placements"](placement)
    data, legacy, common = {}, None, None
    for tag in ("P106", "P97"):
        rows = observed
        raw = arm / "ON/observer/events.pfj"
        if tag == "P97":
            raw = archive / "part-97" / SRC["SOURCES"][tag][0] / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](raw)
        need(sha(raw) == journals[tag], "native journal SHA")
        (_, outside), tx, primary, old, recent, lineage = IV["load_arm"](
            archive, tag, rows, seed, previous[tag]
        )
        identity = (tx, primary, lineage)
        need(common is None or identity == common, "T2 route, initial pools or reservation order")
        common = identity
        regs, _, prices = DL["deadline_arm"](rows, tx, old)
        credit, detail = CO["graph_credits"](rows, local, gaps["journals"][tag])
        need(
            len(prices) == 2354 and detail == ref["request"]["eligible_empty_cpu"][tag],
            "consumer coverage or CPU placement",
        )
        reduced, _ = CO["discount"]({tag: (regs, outside)}, {tag: credit["placed"]})[tag]
        need(legacy is None or recent == legacy, "renewed LRU lineage")
        legacy = recent
        events = projection(rows)
        need(
            [v for op, v in events if op == 11]
            == [128 * t.incoming[0] + t.incoming[1] for t in tx],
            "cache decision and priced generation order",
        )
        data[tag] = dict(
            events=events,
            regions=compact_regions(regs, reduced),
            outside=outside,
            control_ns={k: previous[tag][k + "_ns"] for k in ("first_final", "decode")},
            journal_sha256=journals[tag],
        )
    return dict(prefix=prefix, t1=t1, arms=data, legacy=sorted(legacy), lineage=list(common[2]))


def price(arm, hits, placed, free_sets, read_ppm=1_000_000):
    phases = Counter()
    calls = []
    seen = set()
    for num, groups, edges, discounted in arm["regions"]:
        need(
            len(edges) == len(discounted) == 1 + len(groups)
            and all(0 <= v <= w for v, w in zip(discounted, edges, strict=True)),
            "graph edges",
        )
        service = []
        for observed, granted, jobs in groups:
            need(0 <= granted <= observed, "graph credit")
            costs = []
            for key, read, setters in jobs:
                need(key not in seen and min(read, setters) >= 0, "unpriced or repeated job")
                seen.add(key)
                payment = (
                    (0 if free_sets else setters)
                    if key in hits
                    else read * read_ppm // 1_000_000 + setters
                )
                costs.append(payment)
            service.append(B["layer_fourths"](costs))
        graph = [4 * g[int(placed)] for g in groups]
        edge = [4 * x for x in (discounted if placed else edges)]
        phases[phase(num)] += CO["critical_path"](graph, edge, service)
        calls.append(num)
    need(
        calls == list(range(1, 49)) and seen == set(range(1, 2355)) and hits <= seen,
        "complete workload",
    )
    first = arm["outside"]["first_final"] + sum(
        phases[k] for k in ("5", "148", "decode_to_first_content")
    )
    decode = arm["outside"]["decode"] + phases["decode_to_first_content"] + phases["tail"]
    return dict(
        first_final=first, decode=decode, phases_ns=phases, margin_ns=B["margins"](first, decode)
    )


def break_even(arm, hits):
    def fits(ppm):
        return min(price(arm, hits, True, False, ppm)["margin_ns"].values()) >= 0

    if not fits(0):
        return {"status": "NO_GO_FREE_MISSED_READS"}
    lo, hi = 0, 1_000_001
    while hi - lo > 1:
        middle = (lo + hi) // 2
        if fits(middle):
            lo = middle
        else:
            hi = middle
    need(fits(lo) and (hi > 1_000_000 or not fits(hi)), "break-even bracket")
    return dict(max_read_ppm=lo, min_reduction_ppm=1_000_000 - lo)


def grade(basis):
    ref = SRC["pinned"](READY / "renewal/evidence/decision.json", CONTROL)
    need(
        basis["prefix"] == ref["t1"]["t1_prefix_sha256"] and set(basis["arms"]) == {"P97", "P106"},
        "wrong trajectory",
    )
    result = {}
    prior = ref["request"]["full_client_and_decode_ns"]["recent"]
    for tag, arm in basis["arms"].items():
        for graph, placed in (("unchanged", False), ("placed", True)):
            for delivery, free in (("copied", False), ("direct", True)):
                expected = prior[graph][delivery][tag]
                got = price(arm, set(basis["legacy"]), placed, free)
                need(all(got[k] == v for k, v in expected.items()), "published full-client control")
    for cap, name in (
        (0, "off"),
        (69, "recent"),
        (69, "frequency"),
        (353, "recent"),
        (353, "frequency"),
    ):
        arms = {}
        for tag, arm in basis["arms"].items():
            bank = Bank(cap, name == "frequency")
            _, first = bank.replay(basis["t1"], training=True)
            need(sum(a["jobs"] for a in first.values()) == 5727, "T1 jobs")
            initial = sorted(bank.ready)
            hits, second = bank.replay(arm["events"])
            need(sum(a["jobs"] for a in second.values()) == 2354, "T2 jobs")
            paid = price(arm, hits, False, False)
            granted = price(arm, hits, True, True)
            credit = CC["CREDIT"] if tag == "P106" else 0
            arms[tag] = dict(
                t1=first,
                t2=second,
                initial_ready=len(initial),
                end_ready=len(bank.ready),
                hits=len(hits),
                hits_sha256=IV["digest"](sorted(hits)),
                seed_sha256=IV["digest"](initial),
                observer_credit_ns=credit,
                paid=paid,
                granted=granted,
                best_first_margin_ns=granted["margin_ns"]["first_final"] + credit,
            )
            if cap == 353 and name == "frequency":
                arms[tag]["miss_read_limit"] = break_even(arm, hits)
        decision = "INCONCLUSIVE"
        if any(
            min(a["best_first_margin_ns"], a["granted"]["margin_ns"]["decode"]) < 0
            for a in arms.values()
        ):
            decision = "NO_GO_FIXED_POLICY_AND_PRICES"
        elif all(min(a["paid"]["margin_ns"].values()) >= 0 for a in arms.values()):
            decision = "GO_CAUSAL_FIXTURE_ONLY"
        result[f"{name}_{cap}"] = dict(arms=arms, capacity_bytes=cap * stride, decision=decision)
    return dict(status="TRACE_DERIVED", method=METHOD, policy=result, http_requests=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    compute = sub.add_parser("run")
    for name in ("archive", "placement", "new-output-dir"):
        compute.add_argument("--" + name, type=Path, required=True)
    check = sub.add_parser("check")
    check.add_argument("evidence", type=Path)
    args = parser.parse_args()
    need(sha(HERE / "causal.md") == METHOD, "policy protocol")
    if args.action == "check":
        basis = json.loads(gzip.decompress((args.evidence / "causal-input.json.gz").read_bytes()))
        need(
            grade(basis) == json.loads((args.evidence / "causal-grade.json").read_bytes()),
            "causal replay",
        )
        print("PASS causal cache choices and full clocks")
        return
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir()
    try:
        basis = obtain(args.archive, args.placement)
        result = grade(basis)
        save(out / "causal-input.json.gz", basis)
        save(out / "causal-grade.json", result)
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve() if exc.filename else None
        status = (
            "NOT_RUN_RAW_REQUIRED"
            if missing
            and any(missing.is_relative_to(x.resolve()) for x in (args.archive, args.placement))
            else "FAIL"
        )
        save(out / "failure.json", dict(status=status, missing=str(missing)))
        raise
    except Exception as exc:
        save(out / "failure.json", dict(status="FAIL", reason=repr(exc)))
        raise
    print({k: v["decision"] for k, v in result["policy"].items()})


if __name__ == "__main__":
    main()
