"""Bound a direct CPU destination, two-region service and four T1-derived candidates per layer."""

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE / "lookahead.py")
sha, need, limits = (L[k] for k in ("sha", "need", "LIMITS"))
METHOD = "42673170dcc4668adb9f35df4eee79c7b700064d962b355fbd91997f47b53cb7"
LOOK = "a5762857936e4dae626f7f136f9302c98eec47b8a96dadf43315c5fb0067c210"
PRICE = "ddde0867e46a5326db99aed0ef25a772be1590a6a6a2aaf36938b4420306c406"


def train(screen, archive):
    src = screen["SOURCE"]
    ref = run_path(screen["HERE"] / "selection.py")
    arm = archive / "part-106" / src["SOURCES"]["P106"][0] / "ON"
    before = src["pinned"](arm / "before-t2.json", ref["T1_SEAL"])
    reader = ref["PROFILE"]
    rows = list(reader["iter_rows"](arm / "observer/events.pfj", 0, before["records"]))
    grade, _ = reader["prefix_grade"](rows, reader["T1"], 9)
    need(
        len(rows) == 87736 and all(before[k] == v for k, v in grade.items()),
        "historical prefix seal",
    )
    counts = [Counter() for _ in range(36)]
    for e in rows:
        if e.kind == 11:
            counts[e.layer][e.expert] += 1
    ranked = [sorted(c, key=lambda expert, c=c: (-c[expert], expert))[:4] for c in counts]
    need(all(len(v) == 4 for v in ranked), "four candidates per layer")
    return dict(
        status="SEALED_T1_ONLY",
        t1_sha256=ref["T1_SEAL"],
        protocol_sha256=METHOD,
        t1_reservations=sum(c.total() for c in counts),
        ranked=ranked,
    )


def lower(groups, releases, puts):
    # Each half-open interval has a four-worker workload constraint and a longest-job constraint.
    t = [0] * (len(groups) + 1)
    for start in range(len(groups)):
        work = longest = 0
        for dest in range(start, len(groups)):
            for j in groups[dest]:
                cost = puts[j.order] + (j.read if releases[j.order] >= start else 0)
                longest = max(longest, cost)
                work += cost
            t[dest + 1] = max(t[dest + 1], t[start] + max(work, 4 * longest))
    return (t[-1] + 3) // 4


def schedule(groups, lead):
    queues = [deque(g) for g in groups]
    remaining = list(map(len, groups))
    lanes = [None] * 4
    history, opening = {}, [0]
    now = group = 0
    while group < len(groups):
        # Jobs hold the lane, including any interval between the read and the gated SET.
        for lane, j in enumerate(lanes):
            if j is not None and len(history[j.order]) == 5 and history[j.order][-1] == now:
                remaining[j.group] -= 1
                lanes[lane] = None
        while group < len(groups) and remaining[group] == 0:
            opening.append(now)
            group += 1
        if group == len(groups):
            break
        upcoming = []
        for lane, j in enumerate(lanes):
            if j is None:
                queue = next((q for q in queues[group : group + lead + 1] if q), None)
                if queue is not None:
                    j = queue.popleft()
                    lanes[lane] = j
                    history[j.order] = [lane, now, now + j.read]
            if j is None:
                continue
            row = history[j.order]
            if len(row) == 3 and row[2] <= now and j.group == group:
                row.extend((now, now + j.put))
            if row[-1] > now:
                upcoming.append(row[-1])
        need(upcoming, "buffer deadlock")
        now = min(upcoming)
    info = L["audit"](groups, lead, opening, history)
    return now, info, [opening, [[i, *v] for i, v in sorted(history.items())]]


def evaluate(calls, identities, selection, ext, previous, zero_sets):
    by_policy = {
        key: ext.copy()
        for key in ("current", "one", "free_sets", "direct_cpu", "two", "two_schedule", "t1_four")
    }
    counts = Counter()
    witness = []
    peaks = Counter()
    for n, groups in calls.items():
        jobs = [j for g in groups for j in g]
        # Current reservations assign a unique number in the original journal to every generation.
        chosen = {
            j.order for j in jobs if identities[j.order][1] in selection[identities[j.order][0]]
        }
        counts["t1_eligible_generations"] += len(chosen)
        counts["generations"] += len(jobs)
        counts["cpu_generations"] += sum(identities[j.order][0] < 25 for j in jobs)
        puts = {j.order: j.put for j in jobs}
        cpu_direct = {j.order: (0 if identities[j.order][0] < 25 else j.put) for j in jobs}
        here = {j.order: j.group for j in jobs}
        one = {k: max(0, g - 1) for k, g in here.items()}
        two = {k: max(0, g - 2) for k, g in here.items()}
        t1 = {k: (0 if k in chosen else g) for k, g in here.items()}
        actual = {
            "current": lower(groups, here, puts),
            "one": lower(groups, one, puts),
            "free_sets": lower(groups, one, dict.fromkeys(puts, 0)),
            "direct_cpu": lower(groups, one, cpu_direct),
            "two": lower(groups, two, puts),
            "t1_four": lower(groups, t1, puts),
        }
        end, info, events = schedule(groups, 2)
        need(actual["two"] <= end, "lower bound or schedule")
        for key in ("early_buffer_peak", "parked_buffer_peak"):
            peaks[key] = max(peaks[key], info.pop(key))
        counts.update({"schedule_" + k: v for k, v in info.items()})
        actual["two_schedule"] = end
        witness.append(events)
        for policy, ns in actual.items():
            if n <= 46:
                by_policy[policy]["first_final"] += ns
            if n >= 3:
                by_policy[policy]["decode"] += ns
    for policy, lead in (("current", "0"), ("one", "1")):
        need(
            by_policy[policy]
            == {k: v["lower_full_client_ns"] for k, v in previous[lead]["clocks"].items()},
            "wrong per-job release",
        )
    need(
        by_policy["free_sets"] == zero_sets
        and counts["generations"] == counts["schedule_generations"] == 2354,
        "transport floor or conservation",
    )
    counts["t1_eligible_payload_bytes"] = counts["t1_eligible_generations"] * L["PAYLOAD"]
    counts["schedule_early_payload_bytes"] = counts["schedule_early_reads"] * L["PAYLOAD"]
    fits = {k: all(row[m] <= lim for m, lim in limits.items()) for k, row in by_policy.items()}
    decisions = {
        k: "NECESSARY_FLOOR_FITS" if fits[k] else "NO_GO" for k in ("direct_cpu", "t1_four")
    }
    decisions["two"] = (
        "NO_GO"
        if not fits["two"]
        else "GO_TEMPORAL_FIXTURE_ONLY"
        if fits["two_schedule"]
        else "INCONCLUSIVE_SCHEDULE"
    )
    return dict(clocks_ns=by_policy, decision=decisions, counts=dict(counts | peaks)), witness


def score(screen, a):
    need(
        sha(a.lookahead) == LOOK
        and sha(a.price) == PRICE
        and sha(a.bound) == L["PARENT"]
        and sha(a.plan) == a.plan_sha256,
        "parent or causal plan identity",
    )
    plan, look, price, bound = (
        json.loads(p.read_bytes()) for p in (a.plan, a.lookahead, a.price, a.bound)
    )
    need(plan == train(screen, a.archive), "selector used information outside T1")
    src = screen["SOURCE"]
    dead = run_path(screen["HERE"] / "renewal/deadlines.py")
    old = src["pinned"](
        screen["NATURAL"] / "prefill_retention/request_cost/receipt.json", screen["PRIOR"]
    )
    results = {}
    for label in ("P97", "P106"):
        _, auth = screen["read_arm"](a.archive, label, old[label])
        name, digest, _ = src["SOURCES"][label]
        root = a.archive / ("part-" + label[1:]) / name
        if label == "P97":
            rows, _ = src["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
        else:
            _, rows, _, _ = src["Q"]["read_new"](root, digest)
        calls = L["region_jobs"](rows, src, dead)
        identities = [(e.layer, e.expert) for e in rows if e.kind == 11]
        need(
            len(identities) == 2354
            and auth["journal_sha256"] == bound["traces"][label]["journal_sha256"],
            "generation identities",
        )
        report, schedule = evaluate(
            calls,
            identities,
            plan["ranked"],
            auth["outside_calls_ns"],
            look["traces"][label],
            price["traces"][label]["1"]["free_sets"]["current_floor_ns"],
        )
        path = a.new_output_dir / (label + "-two.json")
        with path.open("x") as f:
            json.dump(schedule, f, separators=(",", ":"))
            f.write("\n")
        results[label] = report | dict(
            schedule_sha256=sha(path), journal_sha256=auth["journal_sha256"]
        )
    return dict(
        status="TRACE_DERIVED_ORACLE_AND_CAUSAL_BOUNDS",
        traces=results,
        source_sha256=sha(Path(__file__)),
        protocol_sha256=METHOD,
        plan_sha256=a.plan_sha256,
        model_loads=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["train", "score"])
    p.add_argument("--repo", type=Path, default=HERE.parents[3])
    for k in ("archive", "new-output-dir", "lookahead", "bound", "price", "plan"):
        p.add_argument("--" + k, type=Path, required=k in ("archive", "new-output-dir"))
    p.add_argument("--plan-sha256")
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        need(sha(HERE / "frontier.md") == METHOD, "prospective protocol")
        screen = run_path(a.repo / "research/ready-experts/screen.py")
        result = train(screen, a.archive) if a.action == "train" else score(screen, a)
    except Exception as exc:
        result = dict(
            status="NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            reason=str(exc),
        )
    with (a.new_output_dir / ("plan.json" if a.action == "train" else "frontier.json")).open(
        "x"
    ) as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(
        result["status"] not in ("SEALED_T1_ONLY", "TRACE_DERIVED_ORACLE_AND_CAUSAL_BOUNDS")
    )
