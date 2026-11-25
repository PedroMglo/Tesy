"""Independent checks for the preregistered C305 blocking/continuation experiment."""

import importlib.util
from itertools import pairwise
from pathlib import Path

CONTROL_PATH = Path(__file__).resolve().parents[1] / "manager/verify_result.py"
spec = importlib.util.spec_from_file_location("tesy_blocking_control_verify_result", CONTROL_PATH)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
need, checks = control.need, control.checks
MS = 1_000_000
CONTROLLERS = set(control.CONTROLLER) | {
    "t0",
    "finish_entry",
    "finish_return",
    "finish_throw",
    "new_generation",
}
TRANSFERS = {"defer", "handoff", "continuation_reject", *control.ATTACH}
STAGE = {*control.STAGE, "stage_read_error"}
COMPONENTS = {*control.READ_COPY, "stage_read_error"}


def before(*events):
    need(all(a["seq"] < b["seq"] for a, b in pairwise(events)), "causal order")


def one_worker(*events):
    need(len({r["worker"] for r in events}) == 1, "worker changed mid-service")


class Journal:
    def __init__(self, events):
        need(isinstance(events, list) and 1 <= len(events) <= 256, "bounded journal required")
        self.events = events
        self.index = {}
        self.workers = {}
        self.used = set()
        previous_ns = -1
        for sequence, row in enumerate(events, 1):
            need(isinstance(row, dict) and control.FIELDS <= row.keys(), "missing event fields")
            need(all(type(row[k]) is int for k in control.FIELDS - {"kind"}), "event integer field")
            kind = row["kind"]
            need(
                type(kind) is str
                and row["seq"] == sequence
                and row["ns"] >= 0
                and row["ns"] >= previous_ns
                and row["tid"] > 0,
                "event sequence, clock or TID",
            )
            previous_ns = row["ns"]
            w, e, k = (row[x] for x in ("worker", "expert", "component"))
            if kind in CONTROLLERS:
                need(w == -1, "controller on worker")
            else:
                need(
                    w in range(4) and self.workers.setdefault(w, row["tid"]) == row["tid"],
                    "unstable worker identity",
                )
            if kind == "new_generation":
                checks(row, dict(expert=1, slot=4, generation=2, ticket=0, component=-1))
            elif kind in CONTROLLERS or kind in control.WORKER:
                checks(row, dict(expert=-1, slot=-1, generation=0, ticket=0, component=-1))
            elif kind in STAGE:
                need(e in (1, 2, 3) and row["ticket"] > 0, "invalid stage identity")
                checks(row, dict(slot=-1, generation=0))
            elif kind in TRANSFERS:
                need(row["ticket"] > 0, "absent transfer ticket")
                checks(row, dict(expert=1, slot=4, generation=1))
            else:
                need(kind in (*control.COPY, *control.DIRECT, *control.PRIMARY), "unknown event")
                need(e in ((4,) if kind in control.DIRECT else (1, 4)), "invalid primary expert")
                checks(row, dict(slot=4 if e == 1 else 5, generation=1, ticket=0))
            need((k in range(3) if kind in COMPONENTS else k == -1), "wrong component")
            key = (kind, w if kind in control.WORKER else e, k)
            need(key not in self.index, "duplicate event")
            self.index[key] = row
        need(len(set(self.workers.values())) == 4, "four distinct workers required")
        need(
            not any(r["tid"] in self.workers.values() for r in events if r["worker"] == -1),
            "worker and controller TIDs overlap",
        )

    def get(self, kind, expert=-1, k=-1):
        key = (kind, expert, k)
        need(key in self.index, "missing " + str(key))
        self.used.add(key)
        return self.index[key]

    def components(self, kind, expert):
        return [self.get(f"{kind}_{p}", expert, k) for k in range(3) for p in ("begin", "end")]

    def stage(self, expert):
        start = self.get("stage_start", expert)
        end = self.get("stage_complete", expert)
        io = self.components("stage_read", expert)
        before(start, *io, end)
        one_worker(start, *io, end)
        need(all(row["ticket"] == start["ticket"] for row in (*io, end)), "stage changed ticket")
        return start, end

    def close(self):
        shutdown = self.get("shutdown")
        for w in self.workers:
            enter = self.get("worker_enter", w)
            exit_ = self.get("worker_exit", w)
            before(enter, shutdown, exit_)
            for row in self.events:
                if row["worker"] == w and row["kind"] not in control.WORKER:
                    before(enter, row, shutdown)
        need(self.used == self.index.keys(), "unexpected unfinished, duplicate or extra work")


def verify_gates(raw, j, t0, schedule):
    gates = raw.get("gates")
    need(isinstance(gates, list) and len(gates) == 4, "four gate records required")
    offsets_ms = {1: 450, 2: 250, 3: 350 if schedule == "early" else 1400, 4: 650}
    lates = {}
    for g in gates:
        fields = ("expert", "arrival_ns", "deadline_ns", "opened_ns")
        need(isinstance(g, dict) and all(type(g.get(k)) is int for k in fields), "gate fields")
        expert, arrival, deadline, opened = (g[k] for k in fields)
        need(expert in offsets_ms and expert not in lates, "duplicate or unexpected gate")
        kind = "direct_read" if expert == 4 else "stage_read"
        start = j.get(kind + "_begin", expert, 0)["ns"]
        end = j.get(kind + "_end", expert, 0)["ns"]
        need(start <= arrival <= opened <= end, "gate outside read wrapper")
        anchor = arrival if expert == 4 else t0["ns"]
        need(
            deadline == anchor + offsets_ms[expert] * MS and opened >= deadline,
            "wrong gate deadline",
        )
        if expert != 4:
            need(arrival <= t0["ns"], "producer not at gate when remap started")
        lates[expert] = opened - deadline
    return lates


def check_io(raw, schedule):
    for key in ("issued_components", "delivered_components"):
        expected = [[0] * 3 for _ in range(5)]
        if schedule == "fault":
            expected[1][0] = int(key == "issued_components")
        elif schedule == "stale":
            expected[1] = [1] * 3
        else:
            expected[1:] = [[1] * 3 for _ in range(4)]
        observed = raw.get(key)
        need(
            isinstance(observed, list)
            and len(observed) == 5
            and all(
                isinstance(row, list) and len(row) == 3 and all(type(n) is int for n in row)
                for row in observed
            )
            and observed == expected,
            "component transfer counts: " + key,
        )


def verify_arm(raw: dict, mode: str, schedule: str, arm_dir: Path) -> dict:
    need(mode in ("A", "B") and schedule in ("early", "late"), "unsupported arm")
    checks(raw, dict(mode=mode, schedule=schedule))
    check_io(raw, schedule)
    checks(raw.get("counters"), control.COUNTERS | {"waits": int(mode == "A")})
    checks(raw.get("terminal"), control.TERMINAL | {"pending_continuations": 0})
    j = Journal(raw.get("events"))
    t0, b, bdone, ret, entry, f, fdone, done, shutdown = (
        j.get(kind)
        for kind in (
            "t0",
            "barrier_begin",
            "barrier_end",
            "remap_return",
            "finish_entry",
            "finish_begin",
            "finish_end",
            "finish_return",
            "shutdown",
        )
    )
    before(t0, b, bdone, ret, entry, f, fdone, done, shutdown)
    need(b["tid"] == bdone["tid"] == ret["tid"], "remap thread changed")
    need(entry["tid"] == f["tid"] == fdone["tid"] == done["tid"], "finish thread changed")
    stages = [j.stage(e) for e in (1, 2, 3)]
    seeds, completions = zip(*stages, strict=True)
    need(
        len({s["ticket"] for s in seeds}) == len({s["worker"] for s in seeds}) == 3,
        "three distinct active producers",
    )
    for e, complete in enumerate(completions, 1):
        before(j.get("stage_read_begin", e, 0), t0, complete, fdone)
    a1, a4 = (j.get("primary_accept", e) for e in (1, 4))
    p1, p4 = (j.get("primary_publish", e) for e in (1, 4))
    claim = j.get("claim", 1)
    before(b, a1, a4)
    before(a1, claim)
    need(
        a1["worker"] not in {s["worker"] for s in seeds},
        "fourth worker did not accept attached demand",
    )
    # Source copies each direct component before starting the next positional read.
    direct = j.components("direct_read", 4)
    copies4 = j.components("copy", 4)
    chain = [
        row for k in range(3) for row in (*direct[2 * k : 2 * k + 2], *copies4[2 * k : 2 * k + 2])
    ]
    before(a4, *chain, p4, bdone)
    one_worker(a4, *chain, p4)
    copies1 = j.components("copy", 1)
    before(completions[0], claim, *copies1, p1, bdone)
    one_worker(claim, *copies1, p1)
    if mode == "B":
        defer, handoff = j.get("defer", 1), j.get("handoff", 1)
        before(a1, defer, a4)
        for stop in completions:
            before(a4, stop)
        before(completions[0], handoff, claim)
        one_worker(a1, defer, a4)
        one_worker(seeds[0], handoff, claim, p1)
        attached = (defer, handoff, claim)
    else:
        park, resume = j.get("park", 1), j.get("resume", 1)
        before(a1, park, completions[0], resume, claim)
        one_worker(a1, park, resume, claim, p1)
        need(any(r["seq"] < a4["seq"] for r in completions), "A skipped blocking wait")
        # Any worker serving 4 first had to finish its previous assignment.
        prior = (
            p1
            if a4["worker"] == a1["worker"]
            else next(r for r in completions if r["worker"] == a4["worker"])
        )
        before(prior, a4)
        attached = (park, resume, claim)
    need(all(r["ticket"] == seeds[0]["ticket"] for r in attached), "wrong attached ticket")
    lates = verify_gates(raw, j, t0, schedule)
    j.close()
    dest = control.verify_destinations(raw.get("destinations"), Path(arm_dir))
    return {
        "mechanism": "PASS",
        "mode": mode,
        "schedule": schedule,
        "timing_eligible": max(lates.values()) <= 150 * MS,
        "gate_lateness_ns": {str(k): v for k, v in sorted(lates.items())},
        "remap_ns": ret["ns"] - t0["ns"],
        "finish_ns": done["ns"] - t0["ns"],
        "finish_call_ns": done["ns"] - entry["ns"],
        "through_barrier_ns": bdone["ns"] - t0["ns"],
        "cleanup_after_remap_ns": done["ns"] - ret["ns"],
        "worker_by_producer": [s["worker"] for s in seeds],
        "accept_1_worker": a1["worker"],
        "accept_4_worker": a4["worker"],
        "publish_1_worker": p1["worker"],
        "producer_3_done_after_finish_entry": completions[2]["seq"] > entry["seq"],
        "events": len(j.events),
        "journal_sha256": control.digest(j.events),
        "destinations": dest,
        "destinations_sha256": control.digest(dest),
        "stage_read_components": 9,
        "direct_read_components": 3,
        "copy_components": 6,
        "logical_read_bytes": 12 * control.SLAB,
        "logical_copy_bytes": 6 * control.SLAB,
    }


def compare_family(arms: list[dict]) -> dict:
    order = [(s, m) for s in ("early", "late") for m in ("A", "B", "B", "A")]
    need(
        isinstance(arms, list)
        and len(arms) == 8
        and [(a["schedule"], a["mode"]) for a in arms] == order,
        "eight arms in ABBA order required",
    )
    need(all(a["mechanism"] == "PASS" for a in arms), "unverified arm")
    keys = (
        "destinations_sha256",
        "logical_read_bytes",
        "logical_copy_bytes",
        "stage_read_components",
        "direct_read_components",
        "copy_components",
    )
    need(len({tuple(a[k] for k in keys) for a in arms}) == 1, "unequal work or destination bytes")
    pairs = []
    for offset in range(0, 8, 2):
        a, b = sorted(arms[offset : offset + 2], key=lambda arm: arm["mode"])
        remap = a["remap_ns"] - b["remap_ns"]
        finish = a["finish_ns"] - b["finish_ns"]
        eligible = a["timing_eligible"] and b["timing_eligible"]
        passes = remap > 100 * MS and (
            finish > 100 * MS if a["schedule"] == "early" else abs(finish) < 100 * MS
        )
        pairs.append(
            dict(
                schedule=a["schedule"],
                arms=[offset + 1, offset + 2],
                remap_advantage_ns=remap,
                finish_advantage_ns=finish,
                timing_eligible=eligible,
                timing_gate_met=bool(eligible and passes),
            )
        )
    timing = "PASS" if all(p["timing_gate_met"] for p in pairs) else "INCONCLUSIVE"
    return dict(
        decision=(
            "GO_NATIVE_CONTINUATION_FIXTURE" if timing == "PASS" else "INCONCLUSIVE_FIXTURE_TIMING"
        ),
        mechanism="PASS",
        timing=timing,
        pairs=pairs,
        scope="controlled CPU fixture; fault/stale gates verified separately",
    )


def verify_fault(raw: dict, schedule: str) -> dict:
    """A native reserve/enqueue failure, observed before destruction (no failing graph remap)."""
    need(schedule in ("fault", "stale"), "unsupported fault")
    checks(raw, dict(mode="B", schedule=schedule))
    check_io(raw, schedule)
    stale = schedule == "stale"
    checks(
        raw.get("terminal"),
        control.TERMINAL | dict(pending_continuations=0, load_failed=True, claimed=int(stale)),
    )
    counters = dict(
        issued=1,
        reads=1,
        completed_reads=int(stale),
        expired_running=0,
        waits=0,
        consumed=0,
        errors=int(not stale),
        peak_running_spec=1,
    )
    checks(raw.get("counters"), counters)
    expected = dict(
        slot=4,
        original_generation=1,
        observed_generation=2 if stale else 1,
        observed_expert=1,
        claimed=int(stale),
        state="LOADING",
        finish_threw=True,
        message="CPU staging byte service failed",
        injected_errno=0 if stale else 5,
        restart_rejected=True,
    )
    checks(raw.get("fault"), expected)
    need(not raw.get("destinations"), "failure produced destinations")
    j = Journal(raw.get("events"))
    start, first, stop = (
        j.get("stage_start", 1),
        j.get("stage_read_begin", 1, 0),
        j.get("stage_complete", 1),
    )
    accept, defer, reject = (
        j.get(k, 1) for k in ("primary_accept", "defer", "continuation_reject")
    )
    before(start, first, accept, defer, stop, reject)
    one_worker(accept, defer)
    one_worker(start, first, stop, reject)
    need(accept["worker"] != start["worker"], "producer cannot also own deferred demand")
    need(
        all(r["ticket"] == start["ticket"] for r in (first, stop, defer, reject)),
        "wrong rejected ticket",
    )
    if stale:
        j.stage(1)
        before(defer, j.get("new_generation", 1), j.get("stage_read_end", 1, 0), stop)
    else:
        error = j.get("stage_read_error", 1, 0)
        before(defer, error, stop)
        one_worker(first, error)
        need(error["ticket"] == first["ticket"], "EIO on different ticket")
    entry, finish, fail, shutdown = (
        j.get(k) for k in ("finish_entry", "finish_begin", "finish_throw", "shutdown")
    )
    before(reject, entry, finish, fail, shutdown)
    need(entry["tid"] == finish["tid"] == fail["tid"], "finish error on another thread")
    gates = raw.get("gates")
    need(isinstance(gates, list) and len(gates) == 1, "fault gate count")
    gate = gates[0]
    checks(gate, dict(expert=1, deadline_ns=0))
    need(
        all(type(gate.get(k)) is int for k in ("arrival_ns", "opened_ns"))
        and first["ns"] <= gate["arrival_ns"] <= accept["ns"]
        and defer["ns"] <= gate["opened_ns"] <= stop["ns"],
        "fault gate outside attached read",
    )
    j.close()
    return {
        "mechanism": "PASS",
        "schedule": schedule,
        "level": "native manager reserve/enqueue and error drain",
        "old_generation_published": False,
        "old_generation": 1,
        "observed_generation": expected["observed_generation"],
        "claimed_after_failure": int(stale),
        "completed_stage_components": 3 if stale else 0,
        "load_failed": True,
        "workers_joined": 4,
        "journal_sha256": control.digest(j.events),
        "events": len(j.events),
    }
