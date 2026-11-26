"""C269 T2 own-wave demand service floor with the three observed SETs preserved."""

import argparse
import collections
import importlib.util
from array import array
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
INT = HERE.parent
spec = importlib.util.spec_from_file_location("set_floor_source", INT / "t1_local/source.py")
src = importlib.util.module_from_spec(spec)
spec.loader.exec_module(src)
need, sha = src.need, src.sha
METHOD = "fa949dc8f0fa7ee66326274d8ed64d3acb5269719a26e94ecc9924211a3aa87b"
PREP = "d5321a870115d479ea5d53016a1796bda52dff0d343984d9aa05e92676a384d4"
SCORE = "eb08c93c08201a8074a996a2f898505a452be38f20c03b345df77f9a7a04638a"
CALLBACK_MARGIN = 1_000_000


class Job(NamedTuple):
    key: tuple
    read: int
    copies: int
    first: bool


def bounds(jobs, chosen, a, b):
    costs = [b * j.copies + (a * j.read if j.first and j.key not in chosen else 0) for j in jobs]
    return max([sum(costs), *(4 * value for value in costs)])


def wave(jobs, eligible, a, b):
    """Best measured-price numerator at each exact q; denominator is 4*b."""
    need(jobs and len(jobs) <= 40 and a > 0 and b > 0, "wave geometry/scale")
    removable = {j.key: j for j in jobs if j.first and j.key in eligible}
    need(sum(j.first and j.key in eligible for j in jobs) == len(removable), "duplicate removable")
    need(all(j.read > 0 and j.copies >= 0 for j in jobs), "service price")
    initial = [(j, b * j.copies + (a * j.read if j.first else 0)) for j in jobs]
    maxima = {cost for _, cost in initial} | {b * j.copies for j in removable.values()}
    frontier = [None] * (len(removable) + 1)
    for limit in sorted(maxima):
        if any(
            cost > limit and (not j.first or j.key not in removable or b * j.copies > limit)
            for j, cost in initial
        ):
            continue
        forced = {j.key for j, cost in initial if cost > limit}
        optional = sorted(removable.keys() - forced, key=lambda key: (-removable[key].read, key))
        for q in range(len(forced), len(removable) + 1):
            keys = tuple(sorted(forced | set(optional[: q - len(forced)])))
            candidate = (bounds(jobs, keys, a, b), keys)
            if frontier[q] is None or candidate < frontier[q]:
                frontier[q] = candidate
    need(all(x is not None for x in frontier), "incomplete threshold options")
    return frontier


def solve(groups, eligible, a, b):
    dp = [0]
    steps = []
    first_seen = set()
    for jobs in groups:
        keys = [j.key for j in jobs if j.first]
        need(not set(keys) & first_seen and len(set(keys)) == len(keys), "first key repeats")
        first_seen.update(keys)
        options = wave(jobs, eligible, a, b)
        values = []
        picks = array("B")
        for k in range(len(dp) + len(options) - 1):
            val, q = min(
                (dp[k - q] + options[q][0], q)
                for q in range(max(0, k + 1 - len(dp)), min(k + 1, len(options)))
            )
            values.append(val)
            picks.append(q)
        steps.append((picks, options))
        dp = values

    def choice(k):
        selected = set()
        for prev, options in reversed(steps):
            q = prev[k]
            selected.update(options[q][1])
            k -= q
        need(k == 0, "invalid witness")
        return selected

    return dp, choice


def extract(rows, plan, meta, start, first):
    """Reconcile each full generation before pricing a wave of independent jobs."""
    spans = collections.defaultdict(dict)
    owners = {}
    queues = {}
    service = collections.defaultdict(list)
    demands = collections.defaultdict(set)
    pub = {}
    firsts = {
        (g["site"][2], j["expert"], j["slot"], j["generation"]): g["site"]
        for g in plan
        for j in g["experts"]
    }
    check_first = set()
    for r in rows:
        site = (r.call, r.tile, r.layer, r.wave)
        key = (r.layer, r.expert, r.slot, r.gen)
        if r.kind in (9, 19, 20, 23):
            need(r.kind not in spans[site], "duplicate boundary")
            spans[site][r.kind] = r.ns
        elif r.kind == 11:
            need(key not in owners, "duplicate reservation")
            owners[key] = site
        elif r.kind == 12:
            queues.setdefault(key, (site, r.a))
        elif r.kind == 10:
            demands[site].add(key)
        elif r.kind in (15, 16):
            service[key].append(r)
        elif r.kind == 17:
            need(key not in pub, "duplicate publish")
            pub[key] = r
    count = collections.Counter()
    phases = collections.defaultdict(collections.Counter)
    groups = collections.defaultdict(list)
    for key, site in owners.items():
        why = queues.get(key)
        need(why is not None and why[0] == site, "enqueue origin")
        if why[1] != 0:
            need(why[1] == 2, "first enqueue generation reason")
            count["excluded_preload"] += 1
            continue
        if key not in demands[site]:
            count["excluded_not_demand_in_own_wave"] += 1
            continue
        begin, barrier, ready, end = (spans[site][k] for k in (9, 19, 20, 23))
        need(begin <= barrier <= ready <= end, "callback/barrier span")
        if begin < start + CALLBACK_MARGIN or end > first - CALLBACK_MARGIN:
            count["excluded_outside_or_crossing_callback"] += 1
            continue
        records = service[key]
        terminal = pub[key]
        need(
            len(records) == 6 and [r.kind for r in records] == [15, 16] * 3, "three READ/SET pairs"
        )
        need(
            len({r.worker for r in [*records, terminal]}) == 1
            and len({r.component for r in records}) == 3
            and all((r.call, r.tile, r.layer, r.wave) == site for r in [*records, terminal])
            and begin <= records[0].begin
            and records[-1].ns <= terminal.ns <= ready
            and all(r.begin <= r.ns for r in records)
            and all(x.ns <= y.begin for x, y in zip(records, records[1:], strict=False)),
            "serial worker to publication/barrier",
        )
        layer, expert, slot, _ = key
        for r, s in zip(records[::2], records[1::2], strict=True):
            offset, size = meta[layer, r.component]
            src.admit.t2.planner.selected_range(
                expert, offset, size, r.a, r.b, r.c, src.admit.t2.planner.MODEL_SIZE
            )
            need(
                r.component == s.component
                and r.error == s.error == 0
                and s.a == size
                and s.b == slot * size,
                "SET and primary destination",
            )
        read = sum(r.ns - r.begin for r in records[::2])
        copies = sum(r.ns - r.begin for r in records[1::2])
        first_job = key in firsts
        if first_job:
            need(tuple(firsts[key]) == site, "first job site")
            check_first.add(key)
        groups[site].append(Job((layer, expert), read, copies, first_job))
        count["included"] += 1
        count["first_reads_charged"] += int(first_job)
        count["repeat_reads_granted_free"] += int(not first_job)
        count[
            "published_by_barrier_entry" if terminal.ns <= barrier else "published_during_barrier"
        ] += 1
        stats = phases[
            ("prefill" if site[0] <= 2 else "decode") + "_" + ("cpu" if layer < 25 else "cuda")
        ]
        for name, val in (
            ("jobs", 1),
            ("first_read_jobs", int(first_job)),
            ("set_events", 3),
            ("set_payload_bytes", sum(r.a for r in records[1::2])),
            ("set_worker_ns", copies),
            ("first_read_worker_ns", read if first_job else 0),
            ("granted_repeat_read_worker_ns", read if not first_job else 0),
        ):
            stats[name] += val
    need(check_first == set(firsts), "original first-job coverage")
    need(
        len(owners)
        == count["included"] + sum(n for name, n in count.items() if name.startswith("excluded_")),
        "reservation coverage",
    )
    ordered = sorted(groups, key=lambda site: spans[site][9])
    need(
        all(spans[x][23] <= spans[y][9] for x, y in zip(ordered, ordered[1:], strict=False)),
        "overlapping group walls",
    )
    return [groups[key] for key in ordered], dict(
        reservations=len(owners), groups=len(ordered), counts=count, by_phase_tier=phases
    )


def evaluate(inp, baseline):
    local = baseline["results"]["current"]
    start = int(inp.client["request_started_monotonic"] * 10**9)
    first = start + int(inp.client["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    plan, raw_floor = src.admit.t2.planner.assemble(inp.rows, inp.meta, start, first)
    need(raw_floor == local["original_service_floor_ns"], "same mandatory first READs")
    groups, conservation = extract(inp.rows, plan, inp.meta, start, first)
    need(conservation["counts"]["first_reads_charged"] == local["first_jobs"], "job denominator")
    eligible = set(map(tuple, inp.available["evicted_ready"]))
    volume = src.admit.t2.eligible_sets(inp.rows)["victims"]
    fixed = local["fixed_ns"]
    reference = baseline["results"]["opportunities"]["evicted_ready"]
    need(
        len(eligible) == reference["population"] == 1698 and len(volume) == 852,
        "T1 and T2 populations",
    )
    cases = {}
    for a, b in ((1, 1), (4, 5)):
        curve, choose = solve(groups, eligible, a, b)
        out = []
        for record in reference["rows"]:
            cap = record["capacity"]
            k = min(cap, len(curve) - 1)
            chosen = choose(k)
            extra = sorted(eligible - chosen, key=lambda key: (key not in volume, key))[: cap - k]
            chosen.update(extra)
            need(chosen <= eligible and len(chosen) == min(cap, len(eligible)), "selection")
            numerator = sum(bounds(jobs, chosen, a, b) for jobs in groups)
            need(numerator == curve[k], "full witness recalculation")
            wall = fixed + numerator // (4 * b)
            read_only = record["scales"][f"{a}/{b}"]["first_floor_ns"]
            need(wall >= read_only, "increased service below original")
            volume_bytes = (len(volume) - len(chosen & volume)) * src.possible.warm.PAYLOAD
            optimistic_volume = (
                len(volume) - min(cap, len(volume & eligible))
            ) * src.possible.warm.PAYLOAD
            decisions = {
                n: (
                    "NO_GO_FIXED_OBSERVED_SET_AND_RELEASE"
                    if wall > 10**10 or optimistic_volume > limit
                    else "HEADROOM_ONLY"
                    if volume_bytes <= limit
                    else "INCONCLUSIVE_VOLUME_TRADEOFF"
                )
                for n, limit in local["budgets"].items()
            }
            residual = collections.Counter()
            for jobs in groups:
                tier = "cpu" if jobs[0].key[0] < 25 else "cuda"
                residual[tier] += sum(j.read for j in jobs if j.first and j.key not in chosen)
            out.append(
                dict(
                    capacity=cap,
                    selected_keys=len(chosen),
                    selected_prefill_volume=len(volume & chosen),
                    selected_sha256=src.audit.digest(sorted(chosen)),
                    first_floor_ns=wall,
                    service_numerator=numerator,
                    service_denominator=4 * b,
                    minimum_service_wall_ns=numerator // (4 * b),
                    remaining_first_read_worker_ns_unscaled=dict(residual),
                    read_only_optimum_ns=read_only,
                    added_wall_floor_ns=wall - read_only,
                    allowed_increment_over_read_only_ns=10**10 - read_only,
                    remaining_time_budget_ns=10**10 - wall,
                    prefill_volume_floor_bytes=volume_bytes,
                    best_possible_volume_bytes=optimistic_volume,
                    decisions=decisions,
                )
            )
        cases[f"{a}/{b}"] = out
    return dict(
        cases=cases,
        selection_population=len(eligible),
        volume_population=len(volume),
        first_fixed_ns=fixed,
        first_service_budget_ns=10**10 - fixed,
        first_reads_only_k0_ns=raw_floor,
        volume_budget_bytes=local["budgets"],
        conservation=conservation,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("part", "model", "inventory", "prepared-dir", "score-dir", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        need(sha(HERE / "protocol.md") == METHOD, "freeze")
        prep = src.pinned(a.prepared_dir / "receipt.json", PREP)
        base = src.pinned(a.score_dir / "receipt.json", SCORE)
        need(
            prep["status"] == "PASS_PREFIX_ONLY"
            and sha(a.prepared_dir / "selection.json") == prep["selection_sha256"]
            and base["status"] == "PASS_SINGLE_SESSION_DIAGNOSTIC"
            and base["archive_manifest"] == src.PART
            and base["prepared_sha256"] == PREP
            and base["source_sha256"] == sha(INT / "t1_local/source.py")
            and base["pricing_sha256"] == sha(INT / "t1_local/evaluate.py"),
            "local input receipts",
        )
        inp = src.load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
        need(inp.journal == base["journal_sha256"], "same capture")
        result = dict(
            status="PASS_CONDITIONAL_SET_SERVICE_FLOOR",
            capture_status="FAIL_PRESERVED",
            archive_manifest=src.PART,
            journal_sha256=inp.journal,
            preparation_sha256=PREP,
            historical_local_score_sha256=SCORE,
            source_sha256=base["source_sha256"],
            new_target_forwards=0,
            **evaluate(inp, base),
        )
    except (ValueError, IndexError, KeyError, TypeError, OSError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(protocol_sha256=METHOD, program_sha256=sha(Path(__file__)))
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
