"""Build the C305 ticket fixture from Tesy's patches; verify real-thread observer OFF/ON."""
import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
HEADERS = {
    "c291-direct-reader.h": ("c291-integral-expert-store.patch",
                             "cb386577d0b424d531a484d81619e29887b2419dd03c05578004b0878f601af6"),
    "c305-cpu-stage.h": ("c305-cpu-prediction-staging.patch",
                         "fe93a2460a22412bc3ccf15596e370e3bed79db2df13a8425e5e053dfac306d0"),
}
MIB = 2**20


def sha(b):
    return hashlib.sha256(b).hexdigest()


def need(ok, why):
    if not ok:
        raise ValueError(why)


class Event(NamedTuple):
    seq: int
    ns: int
    worker: int
    tid: int
    kind: str
    job: int
    comp: int
    slot: int
    generation: int
    ticket: int


def parse(text):
    records = defaultdict(list)
    for line in text.splitlines():
        tag, *fields = line.split()
        need(tag in {"metrics", "work", "dest", "event"}, "unknown output")
        records[tag].append(fields)
    (metrics,) = records["metrics"]
    count, overflow, *counters = map(int, metrics)
    need(overflow == 0, "journal overflow")
    need(counters == [3, 3, 2, 1, 1, 1, 0], "C305 terminal counters")
    work = [list(map(int, row)) for row in records["work"]]
    need(work == [[0, 3, 0], [1, 3, 0], [2, 3, 0], [3, 0, 3], [4, 3, 3]], "component counts")
    dest = {}
    for slot, generation, payload in records["dest"]:
        key = int(slot), int(generation)
        need(key not in dest, "duplicate destination")
        dest[key] = bytes.fromhex(payload)
    canonical = {
        (11, 2): bytes((19 + 13*c + 7*b) % 256 for c in range(3) for b in range(64)),
        (17, 3): bytes((207 + 13*c + 7*b) % 256 for c in range(3) for b in range(64)),
    }
    need(dest == canonical, "destination bytes or generation")
    events = [Event(*map(int, row[:4]), row[4], *map(int, row[5:])) for row in records["event"]]
    need(len(events) == count, "journal count")
    return events, {f"{s}/{g}": sha(b) for (s, g), b in dest.items()}


def verify(events):
    indices = defaultdict(list)
    tids = defaultdict(set)
    for i, e in enumerate(events, 1):
        need(e.seq == i and e.ns >= 0 and (i == 1 or events[i - 2].ns <= e.ns),
             "sequence or clock")
        need(e.worker in range(-1, 4), "unknown worker")
        tids[e.worker].add(e.tid)
        indices[e.kind, e.job, e.comp].append(e)
        slot, gen = {3: (11, 2), 4: (17, 3)}.get(e.job, (-1, 0))
        ticket = {0: 1, 1: 2, 2: 3, 3: 1}.get(e.job, 0)
        need((e.slot, e.generation, e.ticket) == (slot, gen, ticket), "generation/ticket identity")
    need(set(tids) == set(range(-1, 4)) and all(len(v) == 1 for v in tids.values())
         and len(set.union(*tids.values())) == 5, "stable worker/TID bijection")

    def one(kind, job=-1, comp=-1):
        hits = indices[kind, job, comp]
        need(len(hits) == 1, f"expected one {kind} {job} {comp}")
        return hits[0]

    def ordered(*rows):
        need(all(a.seq < b.seq for a, b in zip(rows, rows[1:], strict=False)), "causal order")

    def require_ids(rows, worker):
        need(all(e.worker == worker for e in rows), "work migrated across workers")

    dispatch = [one("dispatch", j) for j in range(5)]
    enqueues = [one("enqueue", j) for j in range(5)]
    require_ids(enqueues, -1)
    terminal = [one("producer_done", j) if j < 3 else one("publish", j) for j in range(5)]
    gate = {j: one("gate_open", j, 0) for j in [0, 1, 2, 4]}
    require_ids(gate.values(), -1)
    for j in range(5):
        if j < 3:
            spans = [(p, k) for k in range(3) for p in ["read_begin", "read_end"]]
        elif j == 3:
            spans = [(p, k) for k in range(3) for p in ["copy_begin", "copy_end"]]
        else:
            spans = [(p, k) for k in range(3) for p in
                     ["read_begin", "read_end", "copy_begin", "copy_end"]]
        service = [one(p, j, k) for p, k in spans]
        ordered(enqueues[j], dispatch[j], *service, terminal[j])
        require_ids([*service, terminal[j]], dispatch[j].worker)
        if j in gate:
            ordered(service[0], gate[j], service[1])
    need(len({e.worker for e in dispatch[:4]}) == 4 and dispatch[4].worker == dispatch[1].worker,
         "required four-worker handoff")
    attach, park, resume, claim, release = [
        one(name, 3) for name in ["attach", "demand_park", "demand_resume", "claim", "release"]]
    require_ids([attach, park, resume, claim, release], dispatch[3].worker)
    for j in [1, 2]:
        ordered(dispatch[j], one("cancel", j), enqueues[3])
    ordered(dispatch[0], enqueues[3], enqueues[4], one("barrier_begin"), dispatch[3], attach, park,
            gate[1], terminal[1], dispatch[4], one("read_begin", 4, 0), gate[0], terminal[0],
            resume, claim, one("copy_begin", 3, 0), one("copy_end", 3, 2), release, terminal[3],
            gate[4], terminal[4], one("barrier_end"), one("drain_begin"), one("drain_end"))
    ordered(gate[2], terminal[2], gate[4])
    controller_tasks = {"cancel", "barrier_begin", "barrier_end", "drain_begin", "drain_end"}
    for e in events:
        if e.kind in controller_tasks:
            need(e.worker == -1, "controller ownership")
    known = {"worker_enter", "worker_exit", "idle_wait", "idle_resume", "enqueue", "dispatch",
             "read_begin", "read_end", "copy_begin", "copy_end", "producer_done", "attach",
             "demand_park", "demand_resume", "claim", "release", "gate_open", "publish"}
    need(all(e.kind in known | controller_tasks for e in events), "unknown event kind")
    for worker in range(4):
        lifetime = [e for e in events if e.worker == worker]
        history = [e.kind for e in lifetime]
        need(history.count("worker_enter") == history.count("worker_exit") == 1
             and history[0] == "worker_enter" and history[-1] == "worker_exit",
             "worker lifecycle")
        ordered(one("drain_begin"), lifetime[-1], one("drain_end"))
        idle = [k for k in history if k in ("idle_wait", "idle_resume")]
        need(idle == ["idle_wait", "idle_resume"] * (len(idle) // 2), "incomplete pool wait")
    need(events[-1].kind == "drain_end", "unfinished drain")
    return {"workers": 4, "saturated_at_attach": True, "head_dispatched_from": "cancelled_producer",
            "last_publication": "direct", "drain_after_join": True,
            "worker_by_dispatch": [e.worker for e in dispatch],
            "controlled_fixture_spans_ns": {
                "demand_park_to_resume": resume.ns - park.ns,
                "blocked_dispatch_to_direct_dispatch": dispatch[4].ns - dispatch[3].ns,
                "direct_publish_minus_blocked_publish": terminal[4].ns - terminal[3].ns,
                "last_publish_to_barrier_end": one("barrier_end").ns - terminal[4].ns,
                "drain_begin_to_joined_end": one("drain_end").ns - one("drain_begin").ns,
            }}


def limit():
    resource.setrlimit(resource.RLIMIT_AS, (256*MIB, 256*MIB))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256*MIB, 256*MIB))


def command(argv, out, name, env=None):
    start = time.monotonic()
    with (out / f"{name}.out").open("x") as stdout, (out / f"{name}.err").open("x") as stderr:
        cmd = ["/usr/bin/time", "-f", "%M", "-o", str(out / f"{name}.rss"), *argv]
        with subprocess.Popen(cmd, cwd=out, stdout=stdout, stderr=stderr, env=env,
                              preexec_fn=limit, start_new_session=True) as proc:
            try:
                code = proc.wait(timeout=60)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                os.killpg(proc.pid, signal.SIGKILL)
                raise
            if code:
                raise subprocess.CalledProcessError(code, cmd)
    return {"wall_s": round(time.monotonic() - start, 6),
            "peak_rss_kib": int((out / f"{name}.rss").read_text())}


def expect_failure(call, message):
    try:
        call()
    except ValueError as exc:
        need(message in str(exc), f"wrong failure: {exc}")
        return str(exc)
    raise ValueError(f"fault accepted: {message}")


def run(repo, out):
    repo, out = repo.resolve(), out.resolve()
    out.mkdir()
    receipt = {"schema": "tesy-c305-observer-native-fixture-v1", "status": "FAIL", "arms": [],
               "protocol_sha256": sha((HERE / "protocolo.md").read_bytes()),
               "fixture_sha256": sha((HERE / "fixture.cpp").read_bytes()),
               "verifier_sha256": sha(Path(__file__).read_bytes()), "headers": {}}
    try:
        for header, (patch, expected) in HEADERS.items():
            command(["git", "apply", f"--include=src/{header}", str(repo / "patches" / patch)],
                    out, header, env=os.environ | {"GIT_CEILING_DIRECTORIES": str(out.parent)})
            need(sha((out / "src" / header).read_bytes()) == expected, "C317 source pin mismatch")
            receipt["headers"][header] = expected
        compiler = os.environ.get("CXX", "c++")
        command([compiler, "--version"], out, "compiler")
        receipt["compiler"] = (out / "compiler.out").read_text().splitlines()[0]
        binary = out / "fixture"
        receipt["build"] = command([compiler, "-std=c++17", "-O2", "-pthread", "-Wall", "-Wextra",
                                    "-Werror", "-I", str(out / "src"), str(HERE / "fixture.cpp"),
                                    "-o", str(binary)], out, "build")
        receipt["binary_sha256"] = sha(binary.read_bytes())
        arms = {}
        for n, mode in enumerate(["off", "on", "on", "off", "overflow"], 1):
            name = f"arm-{n}-{mode}"
            usage = command([str(binary), mode], out, name)
            raw = (out / f"{name}.out").read_text()
            if mode == "overflow":
                overflow = expect_failure(lambda value=raw: parse(value), "journal overflow")
                receipt["faults"] = {"overflow": overflow}
                break
            events, destination = parse(raw)
            need(bool(events) == (mode == "on"), "observer mode")
            row = {"mode": mode, "events": len(events), "destinations_sha256": destination,
                   "local_stdout_sha256": sha(raw.encode()),
                   "process": usage}
            if events:
                row["causality"] = verify(events)
                arms[n] = events
            receipt["arms"].append(row)
        faults = receipt["faults"]
        for name, predicate, expected in [
                ("lost_component", lambda e: e.kind == "read_end" and e.job == 4 and e.comp == 1,
                 "expected one read_end"),
                ("incomplete_terminal", lambda e: e.kind == "drain_end", "expected one drain_end")]:
            kept = [e for e in arms[2] if not predicate(e)]
            need(len(kept) == len(arms[2]) - 1, "mutation changed wrong record count")
            resequenced = [e._replace(seq=i) for i, e in enumerate(kept, 1)]
            faults[name] = expect_failure(lambda rows=resequenced: verify(rows), expected)
        original = (out / "arm-1-off.out").read_text()
        faults["bad_destination"] = expect_failure(
            lambda: parse(original.replace("dest 11 2 13", "dest 11 2 12")), "destination bytes")
        receipt["c305_counters_per_arm"] = {"issued": 3, "completed_reads": 3, "expired_running": 2,
                                            "consumed": 1, "waits": 1, "errors": 0}
        receipt["fixture_payload_bytes_per_arm"] = {"component_size": 64, "staged_reads": 576,
                                                    "direct_reads": 192, "destination_copies": 384}
        receipt["status"] = "PASS_MODEL_FREE_BLOCKING_OBSERVER"
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
        receipt["failure"] = str(exc)
    finally:
        receipt["local_payload_bytes_before_receipt"] = sum(
            p.stat().st_size for p in out.rglob("*") if p.is_file())
        part = out / "receipt.json.part"
        with part.open("x") as f:
            json.dump(receipt, f, indent=2, allow_nan=False)
            f.write("\n")
        part.rename(out / "receipt.json")
    print(receipt["status"], receipt.get("failure", ""))
    return int(receipt["status"] != "PASS_MODEL_FREE_BLOCKING_OBSERVER")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.repo, args.new_output_dir))
