"""Read the two complete, prespecified prefill queues with four persistent workers."""

import argparse
import hashlib
import os
import signal
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
NAT = HERE.parents[2]
ref = run_path(str(NAT / "replay/decode_clock/transport/service/measure.py"))
io, cold, need, clock = (ref[k] for k in ("io", "cold", "need", "clock"))
SIZE, WINDOW, CHUNK = (ref[k] for k in ("SIZE", "WINDOW", "CHUNK"))
CAP, STOP = ref["CAP"], ref["STOP"]
METHOD = "28f495fadbfabb6f2ba58b477a3e467d68f668fbe057a8302c4e57097f27a152"
FRONTIER = "5225590f4a5ea17f7faa1d13fede10dc9abc771d53dbc388333709a4d86765c2"
PLAN = "f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f"
PLAN_RECEIPT = "cdeae2ad6b637c11c1f9dc51ab34664ca756f468ab334f209cca64abd5f3739b"
PASS = "PASS_PREFILL_FULL_QUEUE_PAIR"
EXPECTED = {"R": 13998665728, "P": 13988757504}


def queues(plan):
    need(
        plan["schema"] == "tesy-prefill-transport-v1"
        and plan["component_order"] == ["gate", "down", "up"]
        and plan["model_sha256"] == io.TARGET
        and plan["pack_sha256"] == ref["packlib"]["PACK"]
        and plan["index_sha256"] == ref["packlib"]["INDEX"],
        "source identity",
    )
    data = {5: [], 148: []}
    bank = Counter()
    prev_call = 0
    for group in plan["groups"]:
        tokens = group["call_tokens"]
        need(tokens in data and tokens >= prev_call, "call order")
        prev_call = tokens
        for ordinal, j in enumerate(group["jobs"]):
            layer = group["layer"]
            e = j["expert"]
            need(
                j["ordinal"] == ordinal
                and j["source"] in ("disk", "bank")
                and j["source_enqueue"] in (0, 2)
                and j["pack_bytes"] == WINDOW
                and j["pack_offset"] == (128 * layer + e) * ref["packlib"]["STRIDE"]
                and 0 <= e < 128
                and 0 <= j["slot"] < 40
                and j["generation"] > 0,
                "reservation order/pack",
            )
            if j["source"] == "bank":
                bank[tokens] += 1
                continue
            for ci, (c, role) in enumerate(
                zip(j["components"], plan["component_order"], strict=True)
            ):
                off, src, n = c["source_offset"], c["aligned_offset"], c["aligned_bytes"]
                need(
                    c["role"] == role
                    and c["size_bytes"] == SIZE
                    and 0 <= src == off // 4096 * 4096
                    and n == (off - src + SIZE + 4095) // 4096 * 4096 <= CHUNK
                    and src + n <= cold["MODEL_SIZE"]
                    and c["packed_relative_offset"] == ci * SIZE
                    and len(bytes.fromhex(c["sha256"])) == 32,
                    "GGUF component geometry",
                )
            row = {k: group[k] for k in ("call", "tile", "layer", "wave", "tier")}
            data[tokens].append(dict(**row, **j, index=len(data[tokens])))
    need(tuple(map(len, data.values())) == (34, 1024) and bank == {5: 25, 148: 201}, "population")
    need(
        sum(c["aligned_bytes"] for rows in data.values() for j in rows for c in j["components"])
        == EXPECTED["R"]
        and sum(len(v) * WINDOW for v in data.values()) == EXPECTED["P"],
        "byte census",
    )
    return data


class Monitor:
    def __init__(self, file, sample):
        self.file, self.sample = file, sample
        self.last = clock()
        self.done = threading.Event()
        self.error = None
        self.count = 0
        self.thread = threading.Thread(target=self.run, name="tesy-monitor")

    def observe(self):
        row = self.sample()
        t = clock()
        need(t - self.last < 3_000_000_000, "telemetry gap")
        cold["append_row"](self.file, row)
        self.last = t
        self.count += 1

    def run(self):
        try:
            while not self.done.wait(0.45):
                self.observe()
        except Exception as exc:
            self.error = exc

    def guard(self):
        if self.error:
            raise self.error
        need(clock() - self.last < 3_000_000_000, "telemetry expired")

    def __enter__(self):
        self.observe()
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.done.set()
        self.thread.join(timeout=4)
        need(not self.thread.is_alive(), "monitor termination")
        self.guard()
        self.observe()


def queued_call(pool, fd, buffers, layout, tokens, jobs, guard, *, verify):
    ready = threading.Barrier(5, timeout=5)
    gate = threading.Event()
    lock = threading.Lock()
    abort = threading.Event()
    cursor = 0
    records = [None] * len(jobs)
    extents = [ref["ranges"](layout, j) for j in jobs]

    def worker(nworker):
        nonlocal cursor
        try:
            buf, ptr = buffers[nworker]
            tid = threading.get_native_id()
            ready.wait()
            need(gate.wait(5), "cohort release")
            while not abort.is_set():
                guard()
                with lock:
                    if cursor >= len(jobs):
                        return
                    index = cursor
                    cursor += 1
                    acquired = clock()
                ext, local = extents[index]
                times = io.one_job(fd, ext, [(buf, ptr + n) for n in local])
                hashes = []
                if verify:
                    for i, c in enumerate(jobs[index]["components"]):
                        n = (
                            c["packed_relative_offset"]
                            if layout == "P"
                            else (i * CHUNK + c["source_offset"] - c["aligned_offset"])
                        )
                        with memoryview(buf)[n : n + SIZE] as data:
                            h = hashlib.sha256(data).hexdigest()
                        need(h == c["sha256"], f"payload {layout}/{tokens}/{index}/{i}")
                        hashes.append(h)
                records[index] = (tid, acquired, times, hashes)
        except BaseException:
            abort.set()
            raise

    work = [pool.submit(worker, n) for n in range(4)]
    ready.wait()
    start = clock()
    gate.set()
    for future in work:
        future.result()
    stop = clock()
    need(cursor == len(records) and all(records), "complete queue")
    by_tid = {}
    previous = start
    rows = []
    all_spans = []
    for j, (tid, acquired, spans, hashes) in zip(jobs, records, strict=True):
        need(
            previous <= acquired <= spans[0][0]
            and all(a < b <= stop for a, b in spans)
            and all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False)),
            "FIFO/READ sequence",
        )
        previous = acquired
        thread_spans = by_tid.setdefault(tid, [])
        need(not thread_spans or thread_spans[-1][1] <= acquired, "worker reused while active")
        thread_spans.extend(spans)
        all_spans.extend(spans)
        rr = {
            k: j[k]
            for k in (
                "index",
                "tile",
                "layer",
                "wave",
                "tier",
                "ordinal",
                "expert",
                "slot",
                "generation",
                "source_enqueue",
            )
        }
        rr.update(
            worker=tid,
            acquired_ns=acquired - start,
            read_spans_ns=[[a - start, b - start] for a, b in spans],
        )
        if verify:
            rr["component_sha256"] = hashes
        rows.append(rr)
    hist = Counter()
    outstanding = 0
    previous = start
    for stamp, change in sorted((s, delta) for a, b in all_spans for s, delta in ((a, 1), (b, -1))):
        hist[outstanding] += stamp - previous
        outstanding += change
        need(0 <= outstanding <= 4, "application READ concurrency")
        previous = stamp
    hist[0] += stop - previous
    elapsed = stop - start
    service = sum(b - a for a, b in all_spans)
    need(
        outstanding == 0
        and sum(hist.values()) == elapsed
        and sum(k * v for k, v in hist.items()) == service,
        "concurrency conservation",
    )
    totals = dict(
        call=jobs[0]["call"],
        call_tokens=tokens,
        job_count=len(jobs),
        logical_bytes=len(jobs) * 3 * SIZE,
        requested_bytes=sum(r[3] for ext, _ in extents for r in ext),
        dispatch_to_drain_ns=elapsed,
        read_worker_ns=service,
        read_union_ns=elapsed - hist[0],
        qd_wall_ns={str(i): hist[i] for i in range(5)},
        first_read_ns=min(a for a, _ in all_spans) - start,
        last_read_ns=max(b for _, b in all_spans) - start,
    )
    return totals, dict(**totals, elapsed_ns=elapsed, jobs=rows)


def execute(a, out, result):
    need(io.sha256(HERE / "protocol.md") == METHOD, "method")

    def git(*args):
        return io.call("git", "-C", str(cold["ROOT"]), *args)

    need(git("rev-parse", "HEAD") == a.commit and not git("status", "--porcelain"), "clean commit")
    tree = git("rev-parse", "HEAD^{tree}")
    need(a.plan_sha256 == PLAN and a.plan_receipt_sha256 == PLAN_RECEIPT, "frozen plan and receipt")
    selection = cold["load"](a.plan.with_name("receipt.json"), a.plan_receipt_sha256)
    need(
        selection["status"] == "PASS_ORDERED_PREFILL_TRANSPORT_PLAN"
        and selection["plan_sha256"] == a.plan_sha256,
        "external population seal",
    )
    jobs = queues(cold["load"](a.plan, a.plan_sha256))
    frontier = cold["load"](HERE.parents[1] / "evidence/receipt.json", FRONTIER)
    c55 = cold["load"](a.c55, a.c55_sha256)
    policy = cold["load"](a.c55.with_name("resource-policy.json"), c55["canonical_policy_sha256"])

    def c55_current():
        dt = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
        need(0 <= dt <= 3600, "C55 freshness")

    c55_current()
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and io.operational_session_ready(policy)[0]
        and io.derive_policy(snapshot=policy["snapshot"]) == policy,
        "C55",
    )
    io.CAP, io.STOPS = CAP, STOP
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "scope")
    paths, ids, disk = ref["auth_sources"](a, c55)
    mon = run_path(str(cold["QUAL"] / "packed_layer_service/profile.py"))
    provider, unchanged = mon["monitor_provider"](SimpleNamespace(token=io.stat_id))
    sources = {
        k: dict(
            stat=v,
            layout_sha256=io.TARGET if k == "R" else ref["packlib"]["PACK"],
            placement_sha256=io.PLACEMENT_SHA if k == "R" else ref["PACK_PLACEMENT"],
        )
        for k, v in ids.items()
    }
    order = "RP" if a.process == 1 else "PR"
    if a.process == 2:
        first = cold["load"](a.prior_receipt, a.prior_sha256)
        need(
            first["status"] == PASS
            and first["order"] == "RP"
            and first["process"] == 1
            and all(
                first[k] == v
                for k, v in dict(
                    sources=sources,
                    plan_sha256=a.plan_sha256,
                    plan_receipt_sha256=a.plan_receipt_sha256,
                    monitor_provider=provider,
                    c55_sha256=a.c55_sha256,
                    commit=a.commit,
                    tree=tree,
                ).items()
            ),
            "independent first process",
        )
    else:
        need(a.prior_receipt is a.prior_sha256 is None, "unexpected precursor")
    result.update(
        commit=a.commit,
        tree=tree,
        protocol_sha256=METHOD,
        program_sha256=io.sha256(Path(__file__)),
        process=a.process,
        order=order,
        plan_sha256=a.plan_sha256,
        plan_receipt_sha256=a.plan_receipt_sha256,
        prior_receipt_sha256=a.prior_sha256,
        sources=sources,
        monitor_provider=provider,
        c55_sha256=a.c55_sha256,
        cap_bytes=CAP,
        stop_bytes=STOP,
        arms={},
    )
    raw = out / "raw"
    raw.mkdir(mode=0o700)
    kw = dict(policy=policy, cap_bytes=CAP, expected_power=ref["c135"].POWER)
    inv = ref["c135"].collect(out, a.unit, **kw, sample=lambda: io.monitor(policy)["observation"])
    ref["c135"].require_inventory(out, a.unit, inv, **kw)
    io.save(out / "inventory.json", inv)
    result["inventory_sha256"] = io.sha256(out / "inventory.json")
    c55_current()

    def observe():
        unchanged()
        return io.monitor(policy)

    begin = clock()
    with ExitStack() as stack:
        monitor = stack.enter_context(
            Monitor(stack.enter_context((raw / "telemetry.jsonl").open("x")), observe)
        )
        handles = {}
        for k, p in paths.items():
            handles[k] = os.open(p, os.O_RDONLY | os.O_DIRECT | os.O_NOFOLLOW)
            stack.callback(os.close, handles[k])
            cold["check_fd"](handles[k], p, ids[k])
        buffers = ref["arena"](stack)
        pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
        for verify in (False, True):
            for layout in order:
                phase = layout + ("-integrity" if verify else "")
                result["active_phase"] = phase
                file = raw / (phase + ".jsonl")
                before = io.diskstats(disk)
                reports = []
                details = []
                t = clock()
                for tokens, group in jobs.items():
                    summary, detail = queued_call(
                        pool,
                        handles[layout],
                        buffers,
                        layout,
                        tokens,
                        group,
                        monitor.guard,
                        verify=verify,
                    )
                    reports.append(summary)
                    details.append(detail)
                wall = clock() - t
                after = io.diskstats(disk)
                delta = {k: after[k] - before[k] for k in before}
                need(all(v >= 0 for v in delta.values()), "block counters")
                with file.open("x") as f:
                    for row in details:
                        cold["append_row"](f, row)
                requested = sum(r["requested_bytes"] for r in reports)
                need(requested == EXPECTED[layout], "complete measured byte count")
                if not verify:
                    elapsed = sum(r["dispatch_to_drain_ns"] for r in reports)
                    logical = sum(r["logical_bytes"] for r in reports)
                    result["arms"][layout] = dict(
                        calls=reports,
                        requested_bytes=requested,
                        logical_bytes=logical,
                        raw_sha256=io.sha256(file),
                        dispatch_to_drain_ns=elapsed,
                        wrapper_ns=wall,
                        useful_Bps=logical * 1e9 / elapsed,
                        disk_delta=delta,
                    )
                else:
                    result["arms"][layout].update(
                        verified_components=3 * sum(map(len, jobs.values())),
                        verification_requested_bytes=requested,
                        verification_sha256=io.sha256(file),
                        verification_ns=wall,
                        verification_disk_delta=delta,
                    )
        for k in order:
            cold["check_fd"](handles[k], paths[k], ids[k])
        cleanup = clock()
    result.update(
        cleanup_ns=clock() - cleanup,
        active_family_ns=clock() - begin,
        telemetry_sha256=io.sha256(raw / "telemetry.jsonl"),
        monitor_samples=monitor.count,
        cgroup_peak_bytes=io.scope(),
        frontier_sha256=FRONTIER,
    )
    result["reference"] = frontier["pack_orders"][order]
    need(
        sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) < 32 * 2**20 - 32768,
        "output cap",
    )
    result.update(status=PASS, active_phase=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("commit", "unit", "plan-sha256", "plan-receipt-sha256", "c55-sha256", "prior-sha256"):
        parser.add_argument("--" + k, required=k != "prior-sha256")
    for k in ("plan", "c55", "placement", "pack-placement", "prior-receipt", "new-output-dir"):
        parser.add_argument("--" + k, required=k != "prior-receipt", type=Path)
    parser.add_argument("--process", required=True, type=int, choices=(1, 2))
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)

    def expire(*_):
        raise TimeoutError("physical process 240s deadline")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(240)
    result = dict(status="FAIL_PRESERVED", model_forwards=0, gpu_compute=0)
    try:
        execute(a, a.new_output_dir, result)
    except Exception as exc:
        result.update(reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
        io.save(a.new_output_dir / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    return int(result["status"] != PASS)


if __name__ == "__main__":
    raise SystemExit(main())
