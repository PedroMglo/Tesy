"""Reprice every primary reservation with causal backing tags and actual first use."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(str(HERE.parent / "screen.py"))
L, C, Q, REL = (D[k] for k in ("L", "C", "Q", "REL"))
check, canonical, size, NS = (D[k] for k in ("check", "canonical", "size", "NS"))
PHASES = D["PHASES"]
PREVIOUS = "2c8b361af5ecf04e09643040841ea4d7f59cb0796153b10545367b8f17deacf3"
RULES = "914572faf4acb8745b8187690fbc3d85bb0e2bef5eb5ef524b5672464dd1d914"
BACKEND = "044d8879be19e5c22331a29bf7a273307756de10675b1341ee9d7077e2dabc62"
MODES = ("transient", "worker4", "retain_reads", "retain_evictions_and_reads")


@dataclass(frozen=True)
class Job:
    key: tuple
    site: tuple
    use: tuple
    deadline: int
    set_release: int
    set_ns: int


def verify_reason(why, origin_wave, use_wave):
    # observer.patch: 0=new demand, 2=next-wave preload, 1=promotion of an existing load.
    check(
        (why == 0 and use_wave == origin_wave) or (why == 2 and use_wave == origin_wave + 1),
        "invalid first enqueue or consuming wave",
    )


def jobs(rows, host, tiers, bank):
    waves, reservations = C["timeline"](rows)
    spans = {w.site: (w.start, w.end) for w in waves}
    releases, demands, queues, services = {}, {}, defaultdict(list), defaultdict(list)
    routes = defaultdict(set)
    for (c, t, layer, _), order in Q["L"]["ranks"](rows, 1).items():
        routes[c + 1, t, layer].update(order)
    for r in rows:
        k, site = C["key"](r), C["origin"](r)
        if r.kind == 10:
            demands.setdefault(k, site)
        elif r.kind == 11:
            releases[k] = r
        elif r.kind == 12:
            queues[k].append(r)
        elif r.kind in (13, 30, 16, 17):
            services[k].append(r)
    first = REL["scopes"](rows, host)[3]
    strict = Q["L"]["strict_keys"](rows, host)
    initial = {(r.layer, r.expert) for r in rows if r.kind == 5}
    population, joined, seal = Counter(), {}, []
    for k, site in reservations.items():
        use = demands.get(k)
        D["strict"](use is not None and use[:3] == site[:3], "unobserved same-cell use")
        q = queues[k][0]
        check(
            C["origin"](q) == site and k[3] in routes[site[:3]],
            "queue, generation or target rank",
        )
        verify_reason(q.a, site[-1], use[-1])
        finish = spans[use][1]
        read, service, _, _ = REL["price"](services[k], releases[k].ns, finish)
        check(spans[site][0] <= releases[k].ns <= spans[site][1], "reservation outside site")
        key = C["expert"](k)
        ph = C["phase"](site[0])
        strict_first = ph == "prefill" and strict.get(key) == site and first[key] == k
        group = "strict" if strict_first else ("previously_omitted" if ph == "prefill" else ph)
        tier = tiers[key[0]]
        population[f"{group}/{tier}/{'bank' if key in bank else 'pack'}"] += 1
        population[f"{ph}/{'preload' if q.a else 'demand'}"] += 1
        if ph == "prefill":
            cls = "repeated" if first[key] != k else ("initial" if key in initial else "new")
            population[f"prefill/{cls}"] += 1
        joined[k] = Job(key, site, use, finish, spans[site][0], service - read)
        seal.append((k, site, use, q.a))
    check(
        len(joined) == 2354 and sum(v.site[0] < 3 for v in joined.values()) == 1263,
        "complete population",
    )
    omitted = [
        sum(
            n
            for k, n in population.items()
            if k.startswith("previously_omitted/") and k.endswith("/" + lab)
        )
        for lab in ("pack", "bank")
    ]
    check(omitted == [549, 147], "unpriced control")
    return joined, population, D["sha"](canonical(sorted(seal)))


class Store:
    def __init__(self, mode, bank):
        self.mode = mode
        self.bank = bank
        self.available = set()
        self.retain = mode.startswith("retain")
        self.tags = [None] * 4
        self.acquired = Counter()

    def add(self, key, source, tier):
        if key not in self.bank and key not in self.available:
            self.available.add(key)
            self.acquired[source + "/" + tier] += 1

    def evict(self, key, tier):
        if self.mode == "retain_evictions_and_reads":
            self.add(key, "victim", tier)

    def dispatch(self, key, worker):
        if key in self.bank:
            self.tags[worker] = None
            return "bank"
        if key in self.available or (self.mode == "worker4" and self.tags[worker] == key):
            return "staging"
        self.tags[worker] = None
        return "pack"

    def read_done(self, key, worker, tier):
        self.tags[worker] = key
        if self.retain:
            self.add(key, "disk", tier)


def staging(rows, jobs_, bank, tiers, mode):
    store = Store(mode, bank)
    choice, counts, cut = {}, defaultdict(Counter), {}
    for r in rows:
        if r.kind not in (2, 11, 13, 30):
            continue
        if r.kind == 2:
            if r.call in (2, 46, 48):
                cut[C["phase"](r.call)] = {
                    "extra_records": len(store.available),
                    "extra_payload_bytes": len(store.available) * size,
                    "cumulative_acquisitions": dict(store.acquired),
                }
            continue
        k = C["key"](r)
        job = jobs_[k]
        key = job.key
        tier = tiers[r.layer]
        if r.kind == 11:
            check(0 <= r.a < 128 and r.a != r.expert, "victim identity")
            store.evict((r.layer, r.a), tier)
        elif r.kind == 13:
            check(k not in choice and r.worker in range(4), "duplicate dispatch")
            choice[k] = store.dispatch(key, r.worker)
            counts[C["phase"](job.site[0])][tier + "/" + choice[k]] += 1
        elif choice[k] == "pack":
            store.read_done(key, r.worker, tier)
    check(len(choice) == len(jobs_) and set(cut) == set(PHASES), "uncovered work")
    return choice, {"deliveries": counts, "storage": cut}


def set_floor(tasks):
    # One worker per job, four shared workers. All prices are actual SET worker-ns.
    total = sum(w for _, _, w in tasks)
    hidden = L["early_capacity"](tasks, 4, scale=1)
    extra_worker_wall = (total - hidden) // 4
    largest_chain = max((w - (b - a) for a, b, w in tasks), default=0)
    own = defaultdict(list)
    for a, b, w in tasks:
        if a == b:
            own[a].append(w)
    disjoint = sum(REL["four_lanes"](v) for v in own.values())
    return max(extra_worker_wall, largest_chain, disjoint)


def read_tasks(group, predicted, local, limit):
    """Earlier access is granted to the most urgent equivalent work first."""
    check(predicted <= local and all(local <= end for _, end in group), "invalid same-cell release")
    n = len(group)
    capacity = (
        n
        if limit is None
        else sum(sorted(Counter(k for k, _ in group).values(), reverse=True)[:limit])
    )
    return [
        (predicted if i < capacity else local, d, size)
        for i, d in enumerate(sorted(d for _, d in group))
    ]


def analyse_placements(jobs_, choice, marks, shrink, release, allowance):
    tasks, total, sets, cell_jobs = (
        defaultdict(list),
        Counter(),
        defaultdict(list),
        defaultdict(list),
    )
    for k, j in jobs_.items():
        c = j.site[0]
        z = int(c > 2)
        clock = shrink[z]
        cell = j.site[:3]
        deadline = clock(j.deadline)
        sets[cell].append((clock(j.set_release), deadline, j.set_ns))
        if choice[k] == "pack":
            total[c] += size
            cell_jobs[cell].append((j.key, deadline))
    for cell, group in cell_jobs.items():
        c, t, layer = cell
        z = int(c > 2)
        a, b, ranks, tiles, _ = marks[z]
        clock = shrink[z]
        own = (
            ranks[cell][-1]
            if release == "ranks_observed"
            else (tiles[c, t] if layer == 0 else b[c, t, layer - 1])
        )
        if allowance == 0 or layer == 0:
            earlier = own
        else:
            earlier = L["windows"]((*cell, -1), marks[z], 1, release)[0][0]
        check(earlier <= own <= a[cell] or earlier <= own == ranks[cell][-1], "release bracket")
        tasks[c].extend(read_tasks(group, clock(earlier), clock(own), allowance))
    work = Counter()
    for cell, group in sets.items():
        work[cell[0]] += set_floor(group)
    return tasks, total, work


def projected(tasks, total, work, parent, rate, inherited):
    sums = defaultdict(Counter)
    for c in range(1, 49):
        hidden, link, both = D["resources"](total[c], tasks[c], rate, work[c])
        ph = sums[C["phase"](c)]
        ph["scaled_hidden"] += hidden
        ph["net_ns"] += link
        ph["set_ns"] += work[c]
        ph["net_or_set_ns"] += both
    for ph in sums.values():
        ph["hidden_bytes"] = ph.pop("scaled_hidden") // NS
    cbs = [parent["callback_ns"][p] for p in PHASES]

    def measure(field, fixed_decode=False):
        residual = [sums[p][field] for p in PHASES]
        if fixed_decode:
            f = "network_ns" if field == "net_ns" else "network_or_set_ns"
            residual[1:] = [inherited["phases"][p][f] for p in PHASES[1:]]
        result = D["budget"](
            parent["baseline_first_ns"], parent["baseline_decode_ns"], cbs, residual
        )
        return [result["first_margin_ns"], result["decode_margin_ns"]]

    return {
        "phases": sums,
        "free_set_margins_ns": measure("net_ns"),
        "priced_set_margins_ns": measure("net_or_set_ns"),
        "same_previous_decode_priced_set_margins_ns": measure("net_or_set_ns", True),
    }


def assess(rows, tiers, bank, parent):
    host = C["NATIVE"]["host_trace"](rows)
    check(host["first_decode"] == parent["handoff"], "same handoff")
    js, pop, seal = jobs(rows, host, tiers, bank)
    marks = (L["markers"](rows, host), D["decode_markers"](rows, host))
    shrink = [L["contracted"](mark[-1]) for mark in marks]
    out = {}
    for mode in MODES:
        choice, result = staging(rows, js, bank, tiers, mode)
        scenarios = {}
        for release, width in (
            ("ranks_observed", 0),
            ("ranks_observed", 4),
            ("earliest_outer", 4),
            ("earliest_outer", None),
        ):
            tasks, total, work = analyse_placements(js, choice, marks, shrink, release, width)
            for rate in L["RATES"]:
                prev = next(
                    x
                    for x in parent["choices"]
                    if x["bytes_per_s"] == rate
                    and (
                        (width == 0 and x["horizon"] == 0)
                        or (
                            width != 0
                            and x["release"] == release
                            and x["width"] == ("unlimited" if width is None else "four_per_target")
                        )
                    )
                )
                scenarios[f"{release}/{width if width is not None else 'unlimited'}/{rate}"] = (
                    projected(tasks, total, work, parent, rate, prev)
                )
        out[mode] = dict(result, scenarios=scenarios)
    return {"population": pop, "reservation_first_use_sha256": seal, "modes": out}


def run(archive, backend):
    check(
        L["digest"](HERE / "protocol.md") == RULES
        and L["digest"](HERE.parent / "screen.py")
        == "f6ba1e45cd7f8d103e5afe22eca0181505a1287299db965a8b401e220df8fb71"
        and L["digest"](backend / "src/llama-moe-stream.cpp") == BACKEND,
        "inputs",
    )
    prior = D["run"](archive, backend)
    check(D["sha"](canonical(prior)) == PREVIOUS, "joint predecessor")
    refs = C["SOURCES"]
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in refs.items()}
    seal, rows, tiers, _ = Q["read_new"](roots["P106"], refs["P106"][1])
    bank = set(map(tuple, seal["banks"]["prefill"]["ordered_keys"]))
    p106 = assess(rows, tiers, bank, prior["P106"])
    del rows
    _, _, _, audit = C["CHAIN"]["chain"](roots["P97"], refs["P97"][1])
    rows, header = L["T"]["PFJ"]["read_journal"](roots["P97"] / "ON/raw/events.pfj")
    check(header == audit["header"], "P97 journal")
    p97 = assess(rows, tiers, bank, prior["P97"])
    check(
        p97["population"] == p106["population"]
        and p97["reservation_first_use_sha256"] == p106["reservation_first_use_sha256"],
        "cross-session generation or use",
    )
    return {
        "status": "REPRODUCED_ALL_PREFILL_DELIVERIES",
        "protocol_sha256": RULES,
        "code_sha256": L["digest"](Path(__file__)),
        "previous_sha256": PREVIOUS,
        "worker_source_sha256": BACKEND,
        "P97": p97,
        "P106": p106,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "backend", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.archive, a.backend)
    except (OSError, ValueError, KeyError, StopIteration) as e:
        result = {
            "status": "INCONCLUSIVE" if str(e).startswith("INCONCLUSIVE") else "FAIL_PRESERVED",
            "error": type(e).__name__,
            "reason": str(e),
        }
    (a.new_output_dir / "receipt.json").write_bytes(canonical(result))
    print(result["status"])
    raise SystemExit(int(result["status"] != "REPRODUCED_ALL_PREFILL_DELIVERIES"))
