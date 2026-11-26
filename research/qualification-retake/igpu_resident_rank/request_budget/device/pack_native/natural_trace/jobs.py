"""Reconcile C291 packed delivery and report observed service by originating call and tile."""

import collections
import errno
import os
from dataclasses import dataclass, field
from pathlib import Path
from runpy import run_path

PRIOR = run_path(Path(__file__).resolve().parent.parent / "audit.py")
check = PRIOR["check"]
union_ns = PRIOR["union_ns"]
key = PRIOR["identity"]
SLAB, STRIDE, WINDOW = (PRIOR[k] for k in ("SLAB", "STRIDE", "WINDOW"))
PACK_FILE, PACK_READ = 29, 30
EMPTY, LOADING, READY = 0, 1, 2


def inode(source):
    actual = {source[k] for k in ("ino", "inode") if k in source}
    check(
        len(actual) == 1 and int(source["dev"]) >= 0 and int(next(iter(actual))) > 0,
        "device/inode authority",
    )
    return int(source["dev"]), int(next(iter(actual)))


def origin(e):
    return e.call, e.tile, e.layer, e.wave


@dataclass
class Service:
    inherited_claim: bool
    last_ns: int
    heard: bool = False
    final_read: bool = False
    successful: bool = False
    role: int = 0
    worker: int | None = None

    def read(self, r, fd):
        check(
            not self.final_read and self.role == 0 and r.component == -1 and r.fd == fd,
            "pack read after final read/SET or wrong descriptor",
        )
        check(
            r.a == (128 * r.layer + r.expert) * STRIDE and r.b == WINDOW, "pack index address/span"
        )
        check(
            (r.c == -1 and r.error > 0) or (0 <= r.c <= WINDOW and r.error == 0),
            "syscall result/errno",
        )
        if r.c != -1 or r.error != errno.EINTR:
            self.final_read = True
            self.successful = r.c >= 3 * SLAB

    def copy(self, r, fd):
        if self.inherited_claim and not self.heard:
            # Only an unknown contiguous prefix may be absent at the trigger.
            self.final_read = self.successful = True
            self.role = r.component
        check(
            self.final_read and self.successful and 0 <= self.role < 3 and r.component == self.role,
            "SET order/read validity",
        )
        check(
            (r.fd, r.a, r.b, r.c, r.error) == (fd, SLAB, r.slot * SLAB, self.role * SLAB, 0),
            "SET FD/role/slot/staging",
        )
        self.role += 1

    def event(self, r, fd):
        check(
            r.ns >= self.last_ns
            and (
                (r.begin >= self.last_ns and r.begin > 0)
                or (r.begin == 0 and self.inherited_claim and not self.heard)
            ),
            "worker service chronology",
        )
        if r.kind == PACK_READ:
            self.read(r, fd)
        else:
            self.copy(r, fd)
        self.heard = True
        self.last_ns = r.ns

    def finish(self, r):
        check(r.ns >= self.last_ns, "publication before worker completion")
        if r.kind == 17:
            check(
                (self.inherited_claim and not self.heard) or (self.successful and self.role == 3),
                "READY without three valid SETs",
            )
        elif self.heard and not self.successful:
            check(self.final_read and self.role == 0, "failure during an incomplete retry")


@dataclass
class Volume:
    n: collections.Counter = field(default_factory=collections.Counter)
    spans: dict = field(default_factory=lambda: {"read": [], "set": []})

    def add(self, r):
        if r.kind in (11, 13, 14, 17, 18, 28):
            name = {
                11: "reserved",
                13: "dispatched",
                14: "skipped",
                17: "published",
                18: "failed",
                28: "cancelled",
            }[r.kind]
            self.n[name] += 1
        elif r.kind == PACK_READ:
            self.n.update({"attempts": 1, "requested_bytes": r.b, "returned_bytes": max(0, r.c)})
            self.n["retries_eintr"] += int(r.c == -1 and r.error == errno.EINTR)
            self.n["read_errors"] += int(r.c == -1 and r.error != errno.EINTR)
            self.n["short_payload"] += int(0 <= r.c < 3 * SLAB)
            self.n["short_padding"] += int(3 * SLAB <= r.c < WINDOW)
        elif r.kind == 16:
            self.n.update({"sets": 1, "copied_bytes": r.a})
        if r.kind in (PACK_READ, 16):
            if r.begin:
                self.spans["read" if r.kind == PACK_READ else "set"].append((r.begin, r.ns))
            else:
                self.n["missing_start"] += 1

    def summary(self):
        spans = self.spans["read"] + self.spans["set"]
        result = dict(self.n)
        for name, entries in (*self.spans.items(), ("service", spans)):
            result[name + "_worker_ns"] = sum(end - start for start, end in entries)
            result[name + "_wall_union_ns"] = union_ns(entries)
        return result


def audit_jobs(rows, pack_identity, original_identity):
    """Requires sealed PFJ rows. Missing pre-trigger origin stays explicit and unpriced."""
    check(
        rows and rows[-1].kind == 25 and sum(r.kind == 25 for r in rows) == 1, "missing final join"
    )
    check(
        all(
            0 < r.kind <= 30 and r.reserved == 0 and 0 <= r.begin <= r.ns and r.ns > 0 for r in rows
        ),
        "record integrity",
    )
    check(not any(r.kind == 15 for r in rows), "GGUF read inside packed trace")
    pack_key, orig_key = inode(pack_identity), inode(original_identity)
    check(pack_key != orig_key, "pack is original input")
    files = {}
    for kind, identity in ((7, orig_key), (PACK_FILE, pack_key)):
        fds = [r for r in rows if r.kind == kind]
        check(
            len(fds) == 1
            and (fds[0].a, fds[0].b) == identity
            and fds[0].fd >= 0
            and fds[0].c & os.O_DIRECT,
            "live direct FD/inode",
        )
        files[kind] = fds[0].fd
    check(files[7] != files[PACK_FILE], "overlapping FDs")
    meta = {5, 7, 8, PACK_FILE}
    first_tile = next((i for i, r in enumerate(rows) if r.kind in (2, 3)), len(rows))
    check(
        not any(r.kind in meta or (r.kind == 6 and r.b == 1) for r in rows[first_tile:]),
        "late initial metadata",
    )
    first_return = next((i for i, r in enumerate(rows) if r.kind == 1), None)
    check(first_return is not None and rows[first_return].call == 1, "initial ENTER")
    # A worker can finish a read while the initial snapshot owns the manager lock.
    # Ingest only initial metadata ahead of it. Preserve FIFO order for all mutations.
    slots = {}
    expert_slot = {}
    owners = {}
    initial_loading = set()
    unknown = {}
    jobs = {}
    live = {}
    fifo = collections.deque()
    enqueued = set()
    exited = set()
    closed_failed = set()
    cancelled = set()
    failed = []
    weights = {}
    for r in rows[:first_tile]:
        if r.kind == 8:
            k = r.layer, r.component
            check(
                r.fd == files[7]
                and r.component in range(3)
                and r.layer in range(36)
                and k not in weights
                and r.a >= 0
                and r.b > 0,
                "weight binding",
            )
            weights[k] = r.b
        if r.kind == 5:
            place = r.layer, r.slot
            ident = key(r)
            check(
                r.call == 1
                and r.layer in range(36)
                and r.slot in range(40)
                and place not in slots
                and r.a in (EMPTY, LOADING, READY)
                and (r.expert == -1 if r.a == EMPTY else r.expert in range(128))
                and r.b in (0, 1)
                and (not r.b or r.a == LOADING),
                "initial slot",
            )
            slots[place] = ident, r.a
            if r.a != EMPTY:
                check((r.layer, r.expert) not in expert_slot, "duplicate resident/LOADING identity")
                expert_slot[r.layer, r.expert] = r.slot
            if r.a == LOADING:
                owners[ident] = (0, -1, r.layer, -1)
                initial_loading.add(ident)
                unknown[ident] = {"origin": True, "claimed_at_entry": bool(r.b)}
                if r.b:
                    jobs[ident] = Service(True, 0)
        if r.kind == 6 and r.b == 1:
            check(r.call == 1 and r.a == len(fifo), "initial FIFO index")
            fifo.append(key(r))
            enqueued.add(key(r))
    check(len(slots) == 1440 and len(weights) == 108, "complete 36x40 initial snapshot")
    check(len(jobs) <= 4, "too many initial claims")
    # Queues may already contain duplicates of an obsolete reservation. Never make
    # those into new jobs or assign them the successor's call.
    for ident in fifo:
        if ident not in owners:
            unknown[ident] = {"origin": True, "stale_or_completed_initial_queue": True}
        elif ident in initial_loading:
            enqueued.add(ident)
    check(initial_loading <= set(fifo) | set(jobs), "initial loading has no queue/claim")
    overall = Volume()
    by_origin = collections.defaultdict(Volume)
    by_call = collections.defaultdict(Volume)
    return_cuts = []
    pending_return = None
    queue_return = None
    cut_call = None
    n_enqueues = collections.Counter()
    proved_dispatched = set()
    active_call = 0
    active_tile = 0
    remap = None

    def settle():
        check(not pending_return and not queue_return, "missing RETURN snapshot rows")

    for r in rows:
        ident = key(r)
        place = r.layer, r.slot
        if r.kind in meta or (r.kind == 6 and r.b == 1):
            continue
        if r.kind == 1:
            settle()
            check(not active_call and not active_tile, "overlapping host calls")
            active_call = r.call
            continue
        if r.kind == 3:
            check(active_call == r.call and not active_tile, "tile outside call")
            active_tile = r.tile
            continue
        if r.kind == 9:
            check(
                remap is None and (active_call, active_tile) == (r.call, r.tile),
                "remap outside tile",
            )
            remap = origin(r)
            continue
        if r.kind == 23:
            check(remap == origin(r), "unmatched remap")
            remap = None
            continue
        if r.kind == 4:
            check((active_call, active_tile) == (r.call, r.tile) and remap is None, "tile return")
            active_tile = 0
            continue
        if r.kind == 2:
            settle()
            check(
                active_call == r.call and not active_tile and remap is None and r.a == 0,
                "external return",
            )
            check((r.b, r.c) == (len(fifo), len(jobs)), "RETURN queue/claims")
            cut_call = r.call
            pending_return = {sk: sk in jobs for sk, state in slots.values() if state == LOADING}
            queue_return = collections.deque(enumerate(fifo))
            return_cuts.append(
                dict(
                    call=r.call,
                    queued=list(fifo),
                    claimed=len(jobs),
                    pending=sorted(pending_return),
                )
            )
            active_call = 0
            continue
        if r.kind == 26:
            check(
                r.call == cut_call
                and pending_return is not None
                and ident in pending_return
                and r.a == LOADING
                and r.b == int(pending_return.pop(ident)),
                "RETURN slot identity",
            )
            continue
        if r.kind == 6:
            check(
                r.b == 2
                and r.call == cut_call
                and queue_return
                and queue_return.popleft() == (r.a, ident),
                "RETURN FIFO identity",
            )
            continue
        if r.kind in (10, 19, 20, 21, 22, 27):
            continue
        if r.kind == 24:
            check(
                r.worker in range(4) and r.worker not in exited and r.worker not in live,
                "unexpected worker exit",
            )
            exited.add(r.worker)
            continue
        if r.kind == 25:
            settle()
            check(
                not fifo
                and not jobs
                and not live
                and not active_call
                and not active_tile
                and remap is None
                and exited == set(range(4))
                and (r.a, r.b) == (0, 0)
                and r.c in (0, 1),
                "terminal drain",
            )
            check(not failed or bool(r.c) or bool(cancelled), "load failure omitted at final cut")
            continue
        check(
            r.layer in range(36) and r.slot in range(40) and r.expert in range(128) and r.gen > 0,
            "job identity",
        )
        if r.kind not in (PACK_READ, 16):
            settle()
        if r.kind == 11:
            old, state = slots[place]
            check(
                remap == origin(r)
                and state != LOADING
                and r.a == old[3]
                and r.gen == old[2] + 1
                and ident not in owners
                and (r.layer, r.expert) not in expert_slot,
                "invalid slot reservation",
            )
            if old[3] >= 0:
                del expert_slot[r.layer, old[3]]
            slots[place] = ident, LOADING
            expert_slot[r.layer, r.expert] = r.slot
            owners[ident] = origin(r)
        elif r.kind == 12:
            check(
                slots[place] == (ident, LOADING) and r.a in (0, 1, 2) and remap == origin(r),
                "enqueue",
            )
            check(
                (r.a == 1 and ident in enqueued)
                or (r.a != 1 and ident not in enqueued and owners[ident] == origin(r)),
                "demand/preload/promotion",
            )
            n_enqueues[{0: "demand", 1: "promotion", 2: "preload"}[r.a]] += 1
            fifo.append(ident)
            enqueued.add(ident)
            continue
        elif r.kind in (13, 14, 28):
            check(fifo and fifo.popleft() == ident, "FIFO order or duplicate consumption")
            if r.kind == 13:
                check(
                    slots[place] == (ident, LOADING)
                    and ident not in jobs
                    and ident not in proved_dispatched
                    and r.worker in range(4)
                    and r.worker not in live
                    and r.worker not in exited
                    and origin(r) == owners[ident],
                    "claim identity or origin",
                )
                jobs[ident] = Service(False, r.ns, worker=r.worker)
                live[r.worker] = ident
                proved_dispatched.add(ident)
                check(len(jobs) <= 4, "claim limit")
            elif r.kind == 14:
                check(
                    (slots[place] != (ident, LOADING) or ident in jobs)
                    and r.worker in range(4)
                    and r.worker not in live
                    and r.worker not in exited,
                    "unexplained SKIP",
                )
                if slots[place][0] == ident and ident in owners:
                    check(origin(r) == owners[ident], "skip origin")
            else:
                cancelled.add(ident)
        elif r.kind in (PACK_READ, 16, 17, 18):
            check(
                ident in jobs
                and r.worker in range(4)
                and r.worker not in exited
                and origin(r) == owners[ident],
                "event outside claim or borrowed origin",
            )
            job = jobs[ident]
            if job.worker is None:
                check(job.inherited_claim and r.worker not in live, "inherited worker collision")
                job.worker = r.worker
                live[r.worker] = ident
            check(
                job.worker == r.worker
                and live.get(r.worker) == ident
                and slots[place] == (ident, LOADING),
                "stale worker",
            )
            if r.kind in (PACK_READ, 16):
                if r.kind == 16:
                    check(weights[r.layer, r.component] == SLAB, "role slab size")
                job.event(r, files[PACK_FILE])
            else:
                job.finish(r)
                if r.kind == 17:
                    slots[place] = ident, READY
                else:
                    closed_failed.add(ident)
                    failed.append(ident)
                del jobs[ident], live[r.worker]
        else:
            raise ValueError(f"unknown job event {r.kind}")
        src = owners.get(ident, (0, -1, r.layer, -1))
        overall.add(r)
        by_origin[src].add(r)
        by_call[src[0]].add(r)
    check(
        {k for k in owners if k not in initial_loading} <= enqueued, "reservation without enqueue"
    )
    stranded = {sk for sk, state in slots.values() if state == LOADING}
    check(stranded <= closed_failed | cancelled, "terminal LOADING without failure/cancellation")
    # An inherited claim may expose only its suffix.
    totals = overall.summary()
    for v in (
        "reserved",
        "dispatched",
        "sets",
        "published",
        "failed",
        "attempts",
        "retries_eintr",
        "read_errors",
        "short_payload",
        "short_padding",
        "missing_start",
        "cancelled",
        "skipped",
    ):
        totals.setdefault(v, 0)
    totals.update(
        enqueues=sum(n_enqueues.values()),
        promotions=n_enqueues["promotion"],
        worker_exits=len(exited),
        initial_loading=len(initial_loading),
        end_loading=len(stranded),
        final_load_failed=bool(rows[-1].c),
    )
    issues = []
    if unknown:
        issues.append("PRETRIGGER_ORIGIN_OR_SERVICE_UNOBSERVED")
    if totals["missing_start"]:
        issues.append("INTERVAL_CROSSES_TRIGGER_WITHOUT_START")
    return dict(
        status="INCOMPLETE" if issues else "COMPLETE",
        issues=issues,
        counts=totals,
        eligible_clean_run=not (
            issues
            or failed
            or totals["retries_eintr"]
            or totals["read_errors"]
            or cancelled
            or rows[-1].c
        ),
        fds=dict(original=files[7], pack=files[PACK_FILE]),
        by_call=[dict(call=k, **v.summary()) for k, v in sorted(by_call.items())],
        by_origin=[
            dict(call=k[0], tile=k[1], layer=k[2], wave=k[3], **v.summary())
            for k, v in sorted(by_origin.items())
        ],
        return_cuts=return_cuts,
        inherited=[dict(key=k, **v) for k, v in sorted(unknown.items())],
        failed_jobs=failed,
        cancelled_keys=sorted(cancelled),
        terminal_loading=sorted(stranded),
    )
