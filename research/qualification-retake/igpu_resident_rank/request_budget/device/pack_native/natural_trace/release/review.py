"""Price first-use packed jobs at their proved release sites in a qualified natural P."""

from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from runpy import run_path

SERVICE = run_path(Path(__file__).resolve().parents[1] / "jobs.py")
check, identity, origin = (SERVICE[k] for k in ("check", "key", "origin"))
SLAB, WINDOW = SERVICE["SLAB"], SERVICE["WINDOW"]
PAYLOAD = 3 * SLAB
NS = 10**9


def four_lanes(prices):
    return max(max(prices, default=0), sum(prices) // 4)


def scopes(rows, host):
    """Index only events carried by the first two calls; join activity by full identity."""
    spans, opened = {}, {}
    first_reserve, first_demand, reservations, enqueues = {}, {}, {}, {}
    service = defaultdict(list)
    initial = set()
    for r in rows:
        if r.call not in (1, 2):
            continue
        k = identity(r)
        key = r.layer, r.expert
        site = origin(r)
        if r.kind == 5 and r.a in (1, 2):
            initial.add(key)
        elif r.kind == 9:
            check(not opened and site not in spans, "overlapping or duplicate host callback")
            opened[site] = r.ns
        elif r.kind == 23:
            check(site in opened and r.ns >= opened[site], "unpaired callback")
            spans[site] = (opened.pop(site), r.ns)
        elif r.kind == 10:
            first_demand.setdefault(key, (k, site))
        elif r.kind == 11:
            check(k not in reservations, "duplicated reservation")
            first_reserve.setdefault(key, k)
            reservations[k] = (site, r.ns)
        elif r.kind == 12:
            enqueues.setdefault(k, (r.a, site, r.ns))
        elif r.kind in (13, 30, 16, 17):
            service[k].append(r)
    check(not opened, "unclosed callback")
    intervals = [(s[0], a, b) for s, (a, b) in spans.items()]
    check(
        intervals == [v for v in host["callback_spans"] if v[0] in (1, 2)], "different host spans"
    )
    for i, (c, a, b) in enumerate(intervals):
        call = host["calls"][c - 1]
        check(
            call["enter_ns"] <= a <= b <= call["return_ns"]
            and (i == 0 or intervals[i - 1][2] <= a),
            "overlapping or outside host clock",
        )
    return initial, spans, reservations, first_reserve, first_demand, enqueues, service


def price(events, reserve, finish):
    check(
        [r.kind for r in events] == [13, 30, 16, 16, 16, 17],
        "single dispatch/read/three SETs/publish",
    )
    dispatch, read, *tail = events
    sets, pub = tail[:-1], tail[-1]
    check(
        reserve <= dispatch.ns <= read.begin <= read.ns <= pub.ns <= finish
        and dispatch.worker in range(4)
        and all(r.worker == dispatch.worker for r in events),
        "service before release/after use or worker identity",
    )
    check(
        [r.component for r in sets] == [0, 1, 2]
        and all(r.a == SLAB and r.fd == read.fd for r in sets)
        and read.component == -1
        and read.b == WINDOW
        and PAYLOAD <= read.c <= read.b
        and read.error == 0,
        "packed successful range/SETs",
    )
    check(
        all(a.ns <= b.begin <= b.ns for a, b in zip([read, *sets[:-1]], sets, strict=True))
        and sets[-1].ns <= pub.ns,
        "READ/SET overlap inside generation",
    )
    read_ns = read.ns - read.begin
    return (read_ns, read_ns + sum(r.ns - r.begin for r in sets), read.b, read.c)


def volume(prices):
    jobs = len(prices)
    return {
        "jobs": jobs,
        "payload_bytes": jobs * PAYLOAD,
        "requested_bytes": sum(p[2] for p in prices),
        "returned_bytes": sum(p[3] for p in prices),
    }


def summary(groups):
    result = {}
    for label in (1, 2, "total"):
        sub = [v for s, v in groups.items() if label == "total" or s[0] == label]
        result[str(label)] = dict(
            waves=len(sub),
            **volume([p for v in sub for p in v]),
            read_floor_ns=sum(four_lanes([p[0] for p in v]) for v in sub),
            read_set_floor_ns=sum(four_lanes([p[1] for p in v]) for v in sub),
        )
    return result


def projections(public, credit_ns, floor_ns):
    first = Fraction(str(public["first_final_s"])) * NS
    decode = Fraction(str(public["decode_s"])) * NS
    check(first > 0 and decode > 0, "terminal T2 clocks")
    result = {}
    for rate in (6, 8, 10):
        charged = first - credit_ns + floor_ns - max(Fraction(0), decode - Fraction(47 * NS, rate))
        lower = max(0, int(charged))  # round in the mechanism's favour
        result[str(rate)] = {
            "first_final_floor_ns": lower,
            "margin_to_10s_ns": 10 * NS - lower,
            "decision": "NO_GO_FIXED_SCENARIO" if lower > 10 * NS else "HEADROOM_ONLY",
        }
    return result


def scenarios(aggregate, public, replaced, service):
    result = {}
    if service:
        for name in ("read_floor_ns", "read_set_floor_ns"):
            for ratio in (Fraction(1), Fraction(4, 5), Fraction(1, 2)):
                n = int(aggregate[name] * ratio)
                result[f"{name}@{ratio}"] = {
                    "service_floor_ns": n,
                    "rates": projections(public, replaced, n),
                }
    for field in ("payload_bytes", "returned_bytes"):
        for bps in (4_500_000_000, 8_000_000_000):
            n = aggregate[field] * NS // bps
            result[f"{field}@{bps}_Bps"] = {
                "volume_floor_ns": n,
                "rates": projections(public, replaced, n),
            }
    return result


def classify(rows, host, public):
    initial, spans, reserves, first_reserve, demand, enqueue, services = scopes(rows, host)
    check(all(n in range(1, 3) for n, _, _, _ in spans), "non-prefill site")
    kept = defaultdict(list)
    strict = defaultdict(list)
    sources_at_first_demand = {1: [], 2: []}
    counts = Counter()
    horizon_start = host["calls"][0]["enter_begin_ns"]
    horizon_end = host["calls"][1]["return_ns"]
    check(
        0
        < horizon_start
        <= host["calls"][0]["enter_ns"]
        <= host["calls"][0]["return_ns"]
        <= host["calls"][1]["enter_ns"]
        <= horizon_end,
        "prefill horizon",
    )
    min_returned = {}
    for r in rows:
        if (
            r.kind == 30
            and r.call in (1, 2)
            and horizon_start <= r.begin <= r.ns <= horizon_end
            and PAYLOAD <= r.c <= WINDOW
        ):
            key = r.layer, r.expert
            min_returned[key] = min(min_returned.get(key, r.c), r.c)
    for key, (k, site) in demand.items():
        if key in initial:
            counts["initial_ready_or_loading"] += 1
            continue
        # If a prior prefetch was discarded, always grant that first load for the
        # fixed-release floor. Volume still requires one complete source for the pair.
        check(k in reserves and k in enqueue and k in services, "first demand lacks byte witness")
        origin_site, reserve_ns = reserves[k]
        finish = spans[site][1]
        check(
            horizon_start <= reserve_ns <= finish <= horizon_end,
            "first-use provenance outside prefill",
        )
        cost = price(services[k], reserve_ns, finish)
        check(key in min_returned and min_returned[key] <= cost[3], "missing in-window packed read")
        sources_at_first_demand[site[0]].append((*cost[:3], min_returned[key]))
        if k != first_reserve[key]:
            counts["earlier_other_generation"] += 1
            continue
        reason, enq_site, enq_ns = enqueue[k]
        if reason != 0 or enq_site != site or origin_site != site:
            counts["preload_or_other_release"] += 1
            continue
        check(
            spans[site][0] <= reserve_ns <= enq_ns <= services[k][0].ns,
            "own callback release clock",
        )
        kept[site].append(cost)
        if site[-1] in (0, -1):
            strict[site].append(cost)
            counts["first_wave_demand"] += 1
        else:
            check(site[-1] > 0, "unknown wave shape")
            counts["later_wave_possible_preload"] += 1
    # A sufficient short read may have a different returned count after changing
    # the selected generation. General volume guarantees only useful payload.
    a, b = summary(strict), summary(kept)
    horizon = horizon_end - horizon_start
    callbacks = sum(end - start for start, end in spans.values())
    check(0 <= callbacks <= horizon, "overcounted callbacks")
    aggregate = volume([p for group in sources_at_first_demand.values() for p in group])
    result = dict(
        prefill_calls=[5, 148],
        unique_demanded_keys=len(demand),
        unique_nonempty_entry_keys=len(initial),
        unique_first_use=dict(counts),
        prefill_callback_union_ns=callbacks,
        combined_call_envelope_ns=horizon,
        per_wave_fixed_release={"first_wave": a, "as_observed": b},
        earliest_allowed_at_entry=dict(
            volumes=aggregate,
            by_first_demand_call={str(c): volume(v) for c, v in sources_at_first_demand.items()},
            replaceable_interval_ns=horizon,
        ),
    )
    for v in (a, b):
        v["scenarios"] = scenarios(v["total"], public, callbacks, True)
    result["earliest_allowed_at_entry"]["scenarios"] = scenarios(aggregate, public, horizon, False)
    return result


def measure(rows, host, public):
    """Caller validates the P receipt, external FD stats, HTTP cut, route and host via audit_arm."""
    authorities = {}
    for kind, tag in ((7, "original"), (29, "pack")):
        fs = [e for e in rows if e.kind == kind]
        check(len(fs) == 1, "descriptor metadata")
        authorities[tag] = {"dev": fs[0].a, "ino": fs[0].b}
    audit = SERVICE["audit_jobs"](rows, authorities["pack"], authorities["original"])
    if not audit["eligible_clean_run"] or audit["status"] != "COMPLETE":
        return {"status": "INCONCLUSIVE_SERVICE_AT_CAPTURE_BOUNDARY", "issues": audit["issues"]}
    check(
        [c["number"] for c in host["calls"]] == list(range(1, 49))
        and [[t[0] for t in c["geometry"]] for c in host["calls"][:2]]
        == [[5], [32, 32, 32, 32, 20]],
        "natural 5+148 geometry",
    )
    check(
        (public["cache_n"], public["prompt_n"], public["predicted_n"], public["completion_n"])
        == (2044, 153, 47, 47)
        and public["completion"] == "stop",
        "wrong natural P clock/counters",
    )
    return {"status": "MEASURED_PACK_RELEASE_FIXED_SCENARIOS", **classify(rows, host, public)}
