"""Calculate an entire visit using only its released ranks and the manager state at entry."""

import argparse
import gzip
import hashlib
import heapq
import json
import resource
import sys
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission as ad  # noqa: E402
import policy as p  # noqa: E402
import sources as s  # noqa: E402
import switch as sw  # noqa: E402
from screen import write  # noqa: E402

P = run_path(s.READY / "primary/replay.py")
METHOD = "5c73388a5994bd4216d8b455a5690db4b926bb6d7fb4d73486c58e3207b81c12"
RANKS = "925e9d6ec7c1cef5480ff4ade583221bbf3c664096e032e42b442b83640d3fd5"


def initial_snapshot(archive):
    hist = s.SRC["pinned"](P["RE"]["EXCLUSIVE"].parent / "replay/evidence/receipt.json", P["HIST"])
    family = archive / "part-63/tesy-policy-natural-physical-20261125-r02"
    # Authenticate the complete family, then export only its already-published T2-entry state.
    _, slots, words, calls, interval, _, _, origin = P["R"]["sources"](
        family, hist["family_receipt_sha256"]
    )
    return dict(
        slots=slots, words=words, calls=calls, interval=interval, source=origin["policy_sha256"]
    )


def initial_bank(slots):
    file = s.ENTRY / "evidence-entry-20261128-r01/transactions.json.gz"
    p.need(
        s.sha(file) == "a6208d27a2b44a7aef1c56185e320b2af647a5dd0dc5478d46282a8aa45ff730",
        "T1 transactions",
    )
    src = s.E["F"]["unpack"](file)
    seed = [layer * p.EXPERTS + e for layer, _, e, _ in src["initial"] if e >= 0]
    bank = sw.Incumbent(seed)
    for i, (_, _, layer, _, _, e, old) in enumerate(src["prefix"]):
        if layer < p.LAYERS:
            bank.apply(layer, e, old, i)
    p.need(
        bank.prim
        == {i // 40 * p.EXPERTS + row[0] for i, row in enumerate(slots[:1000]) if row[0] >= 0}
        and len(bank.members()) == 1252,
        "P63/P106 T2 entry",
    )
    return bank, len(src["prefix"])


def place(entry, terminal, waves, reverse):
    """Assign physical frames. Only an overflow diagnostic may use addresses above 1,251."""
    owners = sorted(entry, reverse=reverse)
    cap = 1252
    p.need(len(owners) == cap, "expected full CPU materialization")
    where = {key: i for i, key in enumerate(owners)}
    generations = [1] * cap
    free = []
    last = {k: i for i, wave in enumerate(waves) for k in wave}
    allocated, checks, peak = [], 0, cap

    def release(k):
        slot = where.pop(k)
        p.need(owners[slot] == k, "stale release")
        owners[slot] = -1
        heapq.heappush(free, slot)

    for k in entry.difference(terminal, last):
        release(k)
    for i, needed in enumerate(waves):
        for k in sorted(needed.difference(where)):
            if not free:
                free.append(len(owners))
                owners.append(-1)
                generations.append(0)
            frame = heapq.heappop(free)
            p.need(owners[frame] == -1, "reused live frame")
            generations[frame] += 1
            where[k] = frame
            owners[frame] = k
            allocated.append(k)
        refs = [(k, where[k], generations[where[k]]) for k in needed]
        peak = max(peak, len(where))
        p.need(
            len({frame for _, frame, _ in refs}) == len(needed)
            and all(owners[frame] == k and generations[frame] == gen for k, frame, gen in refs),
            "wrong immutable weight or generation",
        )
        checks += len(refs)
        for k in needed - terminal:
            if last[k] == i:
                release(k)
    p.need(
        set(where) == terminal
        and len(where) == len(set(where.values()))
        and len(allocated) == len(set(allocated))
        and set(allocated) == set(last).union(terminal) - entry,
        "terminal membership or extra read",
    )
    return dict(peak=peak, reads=len(allocated), handle_checks=checks)


def plan_visit(mgr, bank, site, ranks, serial, offset):
    """No controls, suffix events, future routers or terminal memberships are parameters."""
    call, tile, layer = site
    cpu = layer < p.LAYERS
    tracked = cpu and call == 2
    entry = bank.members() if tracked else None
    seen = entry.copy() if tracked else None
    length = len(ranks)
    indexes = range((length + 17) // 18) if length > 40 else [-1]
    planned, extras, needs = [], [], []
    native_paid = 0
    for w in indexes:
        additions, demanded = mgr.callback(layer, w, ranks)
        if tracked:
            pool = mgr.pools[layer]
            active = {e for e, _, _ in demanded}
            park = {pool.ids[slot] for slot in pool.parking} if w >= 0 else set()
            p.need(min(park, default=0) >= 0, "unbacked parking")
            needs.append({layer * p.EXPERTS + e for e in active | park})
        for e, slot, gen, old, _ in additions:
            ix = serial + len(planned)
            planned.append([call, tile, layer, slot, gen, e, old])
            if cpu:
                missed = bank.apply(layer, e, old, offset + ix)
                if tracked and missed:
                    k = layer * p.EXPERTS + e
                    native_paid += 1
                    if k in seen:
                        extras.append([ix, k])
                    seen.add(k)
    if not tracked:
        return planned, None
    target = bank.members()
    rec = dict(
        site=list(site),
        native=native_paid,
        extras=extras,
        entry_sha256=p.digest(sorted(entry)),
        terminal_sha256=p.digest(sorted(target)),
    )
    for label, requirements in (
        ("one", needs),
        ("two", [now | then for now, then in zip(needs, needs[1:] + [set()], strict=True)]),
    ):
        order = place(entry, target, requirements, False)
        p.need(
            order == place(entry, target, requirements, True)
            and native_paid - order["reads"] == len(extras),
            "frame permutation or read conservation",
        )
        rec[label] = order
    return planned, rec


def run(initial, routes):
    mgr = P["R"]["Manager"](
        initial["slots"],
        initial["words"],
        initial["calls"],
        initial["interval"],
        [set() for _ in range(36)],
    )
    bank, offset = initial_bank(initial["slots"])
    native, visits = [], []
    for site, packed in routes:
        ranks = [e for word in packed for e in word.to_bytes(4, "little")]
        jobs, visit = plan_visit(mgr, bank, site, ranks, len(native), offset)
        native.extend(jobs)
        if visit:
            visits.append(visit)
    return native, visits


def score(initial):
    source = HERE.parent / "evidence-layer-20261128-r01/reads.json.gz"
    p.need(s.sha(source) == RANKS, "ranks")
    routes = json.loads(gzip.decompress(source.read_bytes()))["plan"]["ranks"]
    native, visits = run(initial, routes)
    # Scoring opens the observed transactions only after every prediction is complete.
    expected, _ = s.E["V"]["sources"]()
    p.need(
        native == expected and len(native) == 2354 and len(visits) == 125,
        "P97/P106 jobs, generations, owners or order",
    )
    p.need(
        all(
            a["terminal_sha256"] == b["entry_sha256"]
            for a, b in zip(visits[:-1], visits[1:], strict=True)
        ),
        "unexplained CPU transition",
    )
    earlier = s.SRC["pinned"](
        HERE / "evidence-switch-20261128-r01/decision.json",
        "df9fb47be61c0c45a66239aa7d86c7edcf60ba306a1db1a762c55525b86cdb76",
    )
    gold = earlier["cases"]["natural_nominal"]
    all_spared = [pair for visit in visits for pair in visit["extras"]]
    p.need(
        all_spared == gold["dispensable_jobs"]
        and [v["native"] for v in visits] == [r["native"] for r in gold["visits"]],
        "blind cohort differs",
    )
    affected = [v for v in visits if v["extras"]]
    fitted = [
        pair for visit in affected if visit["two"]["peak"] <= 1252 for pair in visit["extras"]
    ]
    clocks = gold["clock"] if fitted == all_spared else sw.clocks(fitted)
    return dict(
        schema="tesy.current_router_frames.v1",
        method=METHOD,
        source_sha256=s.sha(Path(__file__)),
        evidence="TRACE_DERIVED_CAUSAL_ROUTER_AND_FORMAL_FRAMES",
        routed_visits=len(routes),
        predicted_reservations=len(native),
        all_jobs_sha256=p.digest(native),
        training_policy=initial["source"],
        calls_148_cpu=len(visits),
        affected=affected,
        fit_jobs=fitted,
        retained_jobs=all_spared,
        two_wave_peak_all=max(v["two"]["peak"] for v in visits),
        one_wave_peak_all=max(v["one"]["peak"] for v in visits),
        read_count=sum(v["two"]["reads"] for v in visits),
        initial_handle_bijections=2,
        saved_client_ns={k: v["saved_ns"]["first"] for k, v in clocks.items()},
        state_chain_sha256=p.digest([[v["entry_sha256"], v["terminal_sha256"]] for v in visits]),
        status="GO_NATIVE_PLANNER"
        if len(fitted) == 11
        else "PARTIAL_TWO_WAVE_CAPACITY"
        if fitted
        else "NO_GO_TWO_WAVE_CAPACITY",
        client_ns_measured=None,
        numerical_forward=False,
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--new", type=Path)
    mode.add_argument("--check", type=Path)
    cli.add_argument("--archive", type=Path)
    a = cli.parse_args()
    p.need(s.sha(HERE / "shadow-protocol.md") == METHOD, "protocol")
    if a.check:
        bits = (a.check / "initial.json.gz").read_bytes()
        result = score(json.loads(gzip.decompress(bits)))
        result["initial_sha256"] = hashlib.sha256(bits).hexdigest()
        p.need(
            result == json.loads((a.check / "decision.json").read_bytes()), "public shadow planner"
        )
    else:
        if not a.archive:
            cli.error("--new requires --archive")
        a.new.mkdir(exist_ok=False)
        try:
            initial = initial_snapshot(a.archive)
            bits = ad.pack(initial)
            result = score(initial)
            result["initial_sha256"] = hashlib.sha256(bits).hexdigest()
            write(a.new / "initial.json.gz", bits)
            write(
                a.new / "decision.json",
                (json.dumps(result, sort_keys=True, indent=2) + "\n").encode(),
            )
        except Exception as exc:
            write(
                a.new / "FAIL.json",
                (json.dumps(dict(error=type(exc).__name__, reason=str(exc))) + "\n").encode(),
            )
            raise
    print(
        result["status"],
        len(result["fit_jobs"]),
        result["two_wave_peak_all"],
        result["saved_client_ns"],
    )


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (900 << 20, 900 << 20))
    main()
