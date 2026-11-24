"""Audit the blocking C317 projection with separate primary and staging clocks."""

import argparse
import json
import sys
from collections import Counter, defaultdict, deque
from operator import itemgetter
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/post-c320"))
import analyse as source  # noqa: E402

SLAB = 4_406_400
WORKERS = 4
COMPONENTS = (0, 1, 2)
P_MUTEX = {2, 3, 4, 5, 10, 11, 12, 14}


class Event(NamedTuple):
    kind: int
    us: int
    call: int
    route: int
    layer: int
    expert: int
    slot: int
    gen: int
    component: int
    size: int
    rows: int

    @property
    def work(self):
        return self.call, self.layer, self.expert, self.slot, self.gen


def require(condition, message):
    if not condition:
        raise ValueError(message)


def primary(text):
    header, *lines = text.splitlines()
    require(header.split() == source.FIELDS, "unknown primary header")
    rows = [Event(*map(int, line.split())) for line in lines]
    require(all(e.kind in range(1, 17) and e.call in range(33) for e in rows),
            "unknown primary event")
    by_call = defaultdict(list)
    for e in rows:
        by_call[e.call].append(e)
    require(set(by_call) == set(range(33)), "incomplete call inventory")
    for events in by_call.values():
        require([e.kind for e in events if e.kind in (15, 16)] == [15, 16]
                and events[0].kind == 15 and events[-1].kind == 16
                and events[0].us < events[-1].us, "incomplete call boundary")
    decode = [e for e in rows if e.call]
    tasks, routes, features = defaultdict(list), defaultdict(list), {}
    slot = {}
    queue = deque()
    depths = [0]
    pending = [0]
    for i, e in enumerate(decode, 1):
        depths.append(depths[-1] + (e.kind == 5) - (e.kind == 10))
        if e.kind == 1:
            key = e.call, e.layer
            require(key not in features and e.rows == 1, "changed feature geometry")
            features[key] = i
        if e.kind in (2, 3, 4, 5, 10, 11, 12, 14):
            routes[e.call, e.layer, e.route].append((i, e))
        if e.kind in range(4, 11):
            tasks[e.work].append((i, e))
        if e.kind == 4:
            queue.append(e.work)
            physical = e.layer, e.slot
            require(0 <= e.slot < 40 and e.gen > slot.get(physical, 0), "stale reservation")
            slot[physical] = e.gen
        elif e.kind == 5:
            require(queue and queue.popleft() == e.work, "acceptance diverges from enqueue FIFO")
        pending.append(len(queue))
    require(not queue and depths[-1] == 0 and min(depths) >= 0, "unfinished primary work")
    by_target = {}
    barriers = []
    wake_slack = []
    for (call, layer, _route), indexed in routes.items():
        group = [e for _, e in indexed]
        kinds = [e.kind for e in group]
        demand = [e for e in group if e.kind == 3]
        reservations = {e.expert: e for e in group if e.kind == 4}
        commits = [e for e in group if e.kind == 10]
        require(kinds[0] == 2 and kinds[-1] == 14 and kinds.count(2) == kinds.count(14) == 1
                and group[0].rows == 1 and len({e.expert for e in demand}) == 4,
                "incomplete router barrier")
        require(all(e.size in (0, 2) for e in demand),
                "unreconciled LOADING hit")
        missing = {e.expert for e in demand if e.slot == -1 and e.size == 0}
        require(set(reservations) == missing == {e.expert for e in commits}
                and len(commits) == len(reservations)
                and all(e.size == 2 and 0 <= e.slot < 40
                        for e in demand if e.expert not in missing),
                "keep set, misses and publications disagree")
        if commits:
            begin = next(e for e in group if e.kind == 11)
            end = next(e for e in group if e.kind == 12)
            last = commits[-1]
            require(kinds.count(11) == kinds.count(12) == 1
                    and begin.us <= last.us <= end.us <= group[-1].us,
                    "last publication does not release the router barrier")
            barriers.append(end.us - begin.us)
            wake_slack.append(end.us - last.us)
        else:
            require(11 not in kinds and 12 not in kinds, "WAIT without pending demand")
        require((call, layer) not in by_target, "multiple routers in one decode layer")
        by_target[call, layer] = (indexed[0][0], next(i for i, e in indexed if e.kind == 3),
                                  {e.expert for e in demand} - missing)
    require(set(by_target) == {(c, layer) for c in range(1, 33) for layer in range(36)},
            "decode call/layer inventory changed")
    for indexed in tasks.values():
        events = [e for _, e in indexed]
        kinds = [e.kind for e in events]
        expected = [4, 5] + [k for _ in COMPONENTS for k in (6, 7, 8, 9)] + [10]
        staged = [4, 5, 8, 9, 8, 9, 8, 9, 10]
        require(kinds in (expected, staged) and len({e.route for e in events}) == 1
                and [e.us for e in events] == sorted(e.us for e in events), "generation lifecycle")
        for kind in ({6, 7, 8, 9} & set(kinds)):
            require([(e.component, e.size) for e in events if e.kind == kind]
                    == [(k, SLAB) for k in COMPONENTS], "projection order/bytes changed")
    last_wait = next(e for e in reversed(decode) if e.kind == 12)
    inversions = sum(a.us > b.us for a, b in zip(decode, decode[1:], strict=False))
    report = {
        "decode_primary_events": len(decode),
        "file_order_clock_inversions": inversions,
        "primary_accepts_publishes": len(tasks),
        "primary_logical_copy_bytes": len(tasks) * 3 * SLAB,
        "resident_selections": 32 * 36 * 4 - len(tasks),
        "explicit_router_waits": len(barriers),
        "router_wait_us": sum(barriers),
        "router_wait_after_last_publication_us": sum(wake_slack),
        "last_route_has_wait": 11 in [e.kind for _, e in routes[next(reversed(routes))]],
        "last_wait_to_call_end32_us": by_call[32][-1].us - last_wait.us,
        "call_end32_minus_prefill_end_us": by_call[32][-1].us - by_call[0][-1].us,
    }
    return decode, tasks, by_target, features, depths, pending, report


def staging(data):
    journal = data["journal"]
    require(data["idle"] and data["enabled"] and data["journal_enabled"]
            and data["fd_O_DIRECT"] and data["arena_bytes"] + data["metadata_bytes"] <= 128 * 2**20
            and len(journal) <= data["journal_capacity"], "staging scope did not drain")
    counts = Counter()
    tickets = defaultdict(list)
    running = set()
    speculative = set()
    live = set()
    depths = [0]
    peak = 0
    for i, e in enumerate(journal, 1):
        ticket = e["scope"], e["ticket"]
        kind = e["kind"]
        require(e["scope"] == 1 and kind in {1, 2, 3, 4, 5, 6, 7, 8, 11}
                and (i == 1 or journal[i - 2]["us"] <= e["us"]), "unqualified stage event")
        seq = tickets[ticket]
        if seq:
            require(all(e[k] == seq[0][1][k] for k in ("call", "layer", "expert")),
                    "ticket identity changed")
        seq.append((i, e))
        if kind == 1:
            live.add(ticket)
        elif kind == 2:
            running.add(ticket)
            speculative.add(ticket)
        elif kind == 3:
            running.remove(ticket)
            speculative.discard(ticket)
        elif kind == 6:
            speculative.discard(ticket)
        elif kind in (4, 8):
            live.remove(ticket)
        require(len(live) <= 10, "stage entry limit")
        peak = max(peak, len(speculative))
        depths.append(len(running))
    require(not running and not live and peak <= 3, "unfinished or over-capacity staging work")

    cycles = {
        (1, 4): "queued_removed",
        (1, 2, 3, 4): "expired_ready",
        (1, 2, 5, 3, 4): "expired_running",
        (1, 2, 3, 6, 7, 11, 8): "ready_attaches",
        (1, 2, 6, 3, 7, 11, 8): "reading_attaches",
    }
    for seq in tickets.values():
        kinds = tuple(e["kind"] for _, e in seq)
        require(kinds in cycles, f"unmatched ticket lifecycle {kinds}")
        counts[cycles[kinds]] += 1
    s = data["stats"]
    consumed = counts["ready_attaches"] + counts["reading_attaches"]
    reads = consumed + counts["expired_ready"] + counts["expired_running"]
    require(s["issued"] == len(tickets) and s["reads"] == s["completed_reads"] == reads
            and reads * 3 * SLAB == s["logical_read_weight_bytes"]
            and s["consumed"] == consumed and s["waits"] == counts["reading_attaches"]
            and s["expired_ready"] == counts["expired_ready"]
            and s["expired_running"] == counts["expired_running"]
            and s["peak_running_spec"] == peak
            and s["errors"] == s["validation_claims"] == s["validation_components"] == 0,
            "staging counters do not conserve lifecycle")
    return tickets, depths, counts, s


def merge(primary_depth, stage_depth, edges):
    """Reachability of all prefix pairs in the capacity-constrained projection."""
    n, m = len(primary_depth) - 1, len(stage_depth) - 1
    lo, hi = [0] * (n + 1), [m] * (n + 1)
    for p, s, primary_first in edges:
        if primary_first:
            hi[p - 1] = min(hi[p - 1], s - 1)
        else:
            lo[p] = max(lo[p], s)
    for p in range(1, n + 1):
        lo[p] = max(lo[p], lo[p - 1])
    for p in range(n - 1, -1, -1):
        hi[p] = min(hi[p], hi[p + 1])
    forward = []
    for p in range(n + 1):
        row = set()
        previous = forward[-1] if p else set()
        for s in range(lo[p], hi[p] + 1):
            if primary_depth[p] + stage_depth[s] <= WORKERS and (
                (p == s == 0) or s in previous or s - 1 in row
            ):
                row.add(s)
        forward.append(row)
    require(m in forward[-1], "no interleaving satisfies the four-worker projection")
    viable = [set() for _ in forward]
    viable[-1].add(m)
    for p in range(n, -1, -1):
        for s in sorted(forward[p], reverse=True):
            if (p < n and s in viable[p + 1]) or s + 1 in viable[p]:
                viable[p].add(s)
    return viable


def locked_attach_edge(accept, attach):
    """All earlier staging records precede accept in this uninterrupted critical section."""
    require(accept >= 1 and attach > 1, "missing prior staging record")
    return accept, attach - 1, False


def audit(text, staged):
    decode, tasks, routes, features, depths, pending, report = primary(text)
    tickets, stage_depth, counts, stats = staging(staged)
    ordinary = {work[:3]: seq for work, seq in tasks.items()
                if any(row.kind == 6 for _, row in seq)}
    prev_mutex, next_mutex = {}, {}
    last = None
    for i, e in enumerate(decode, 1):
        prev_mutex[i] = last
        if e.kind in P_MUTEX:
            last = i
    last = None
    for i in range(len(decode), 0, -1):
        next_mutex[i] = last
        if decode[i - 1].kind in P_MUTEX:
            last = i
    edges = []
    attached = set()
    wait_at = {}
    locked_edges = []
    queued_takeover = 0
    receiver_cancel = 0
    for seq in tickets.values():
        positions = {e["kind"]: i for i, e in seq}
        issue, event = seq[0]
        call, layer, expert = itemgetter("call", "layer", "expert")(event)
        route, classify, hits = routes[call, layer]
        source_layer = layer - 2
        edges.extend([(features[call, source_layer], issue, True),
                      (routes[call, source_layer][0], issue, False)])
        if 6 in positions:
            claim = next(e for _, e in seq if e["kind"] == 7)
            publish = next(e for _, e in seq if e["kind"] == 11)
            work = call, layer, expert, claim["slot"], claim["generation"]
            require((claim["slot"], claim["generation"]) == (publish["slot"], publish["generation"])
                    and work in tasks and work not in attached, "staged generation join")
            attached.add(work)
            require(len(tasks[work]) == 9, "staged ticket also did an original demand read")
            _, accept, first_copy, *_, last_copy, resident = [i for i, _ in tasks[work]]
            locked_edges.append(locked_attach_edge(accept, positions[6]))
            edges.extend([
                (accept, positions[6], True),
                (next_mutex[accept], positions[6], False),
                (first_copy, positions[7], False),
                (last_copy, positions[11], True),
                (prev_mutex[resident], positions[11], True),
                (resident, positions[8], False),
            ])
            if positions[6] < positions[3]:
                wait_at[accept] = positions[6]
            else:
                edges.append((next_mutex[accept], positions[7], False))
        else:
            cancel = positions.get(5, positions[4])
            if len(seq) == 2 and (call, layer, expert) in ordinary and expert not in hits:
                _, (accept, _), (first_read, _), *_ = ordinary[call, layer, expert]
                edges.extend([(accept, cancel, True), (next_mutex[accept], cancel, False),
                              (first_read, cancel, False)])
                queued_takeover += 1
            else:
                # Unselected experts and selected resident hits are cancelled
                # in prediction_router_locked, before classifying the demand.
                edges.extend([(route, cancel, True), (classify, cancel, False)])
                receiver_cancel += 1
    require(attached == {work for work, seq in tasks.items() if len(seq) == 9}
            and len(wait_at) == stats["waits"]
            and counts["queued_removed"] == stats["expired_queued"] + queued_takeover,
            "cross-journal conservation")
    relaxed = merge(depths, stage_depth, edges)
    viable = merge(depths, stage_depth, edges + locked_edges)
    ambiguous = 0
    full = Counter()
    occupied = Counter()
    previously_ambiguous = 0
    example = None
    for p, attach in wait_at.items():
        # Immediately after primary accept, before the matching staging attach.
        prefixes = {s for s in viable[p] if s < attach}
        require(prefixes == {attach - 1}, "nonadjacent locked accept/attach")
        occupancies = {depths[p] + stage_depth[s] for s in prefixes}
        occupied[depths[p] + stage_depth[attach - 1]] += 1
        before_fix = {depths[p] + stage_depth[s] for s in relaxed[p] if s < attach}
        previously_ambiguous += len(before_fix) > 1
        ambiguous += len(occupancies) > 1
        if pending[p]:
            full["pending_accepted_later"] += 1
            full["necessarily_four_busy"] += occupancies == {4}
            full["possibly_four_busy"] += 4 in occupancies
            if example is None and min(before_fix) < 4 and 4 in before_fix:
                e = decode[p - 1]
                example = {"primary_decode_index": p, "staging_attach_index": attach,
                           "call": e.call, "layer": e.layer, "possible_busy": sorted(occupancies),
                           "other_already_queued": pending[p],
                           "old_possible_busy": sorted(before_fix),
                           "primary_assigned": depths[p],
                           "staging_assigned": stage_depth[attach - 1],
                           "locked_stage_prefix": attach - 1}
    return report | {
        "blocking_projection": "CAPACITY_FEASIBLE",
        "complete_timed_blocking_replay": "INCONCLUSIVE",
        "feasible_prefix_pairs": sum(map(len, viable)),
        "primary_direct_reads": len(ordinary),
        "stage_counts": dict(counts),
        "stage_logical_read_bytes": stats["logical_read_weight_bytes"],
        "stage_queued_to_direct": queued_takeover,
        "stage_router_cancellations": receiver_cancel,
        "unlogged_stage_deduplications": stats["deduplicated"],
        "unlogged_refused_forecasts": stats["no_capacity"],
        "ambiguous_occupancy_at_accepts": ambiguous,
        "other_work_at_blocked_accept": dict(full),
        "old_relaxed_ambiguous_accepts": previously_ambiguous,
        "assigned_at_blocked_accept": dict(sorted(occupied.items())),
        "corrected_relaxed_example": example,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    options = parser.parse_args()
    options.output_dir.mkdir()
    manifest = source.required_files()
    missing = [name for name in manifest if not (options.raw_dir / name).is_file()]
    result = {"schema": "tesy-c317-blocking-projection-v2",
              "inputs": manifest, "missing": missing, "arms": {},
              "continuation": {"status": "NOT_RUN", "favorable": None, "with_costs": None,
                               "maximum_admissible_us_per_continuation": None}}
    try:
        if missing:
            result["decision"] = "NOT_RUN_RAW_REQUIRED"
            return 2
        raw = {name: source.checked_bytes(options.raw_dir / name, spec)
               for name, spec in manifest.items()}
        result["decision"] = "INCONCLUSIVE"
        observations = source.archived(f"{source.C317}/observer-analysis.json")["cases"]
        for name in (key.removesuffix("/events.tsv") for key in raw if key.endswith("/events.tsv")):
            text = raw[f"{name}/events.tsv"].decode()
            staged = json.loads(raw[f"{name}/staging.json"])
            prefix = name.removesuffix(".native")
            case = prefix.split("-")[1]
            receipt = json.loads((ROOT / source.C317 / f"{prefix}-analysis.json").read_text())
            from_receipt = {key: receipt[key] for key in ("decode_forward_s", "stage_cleanup_s")}
            result["arms"][name] = audit(text, staged) | source.summarize_trace(text, staged) | {
                "trace_neutral": observations[case]["neutral_timing"],
                "historical_measured_clock_s": receipt["metrics"] | from_receipt,
            }
    except (ValueError, KeyError, OSError) as exc:
        result["failure"] = str(exc)
        result["decision"] = "INCONCLUSIVE"
        return 1
    finally:
        with (options.output_dir / "audit.json").open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
