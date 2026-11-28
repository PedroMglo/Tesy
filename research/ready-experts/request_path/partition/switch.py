"""Switch only the prefill policy; charge every member needed by the original first decode."""

import argparse
import gzip
import hashlib
import json
import resource
import sys
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission as ad  # noqa: E402
import policy as p  # noqa: E402
import sources as s  # noqa: E402
from screen import write  # noqa: E402

METHOD = "078c421adc06e2ca73c5b02befd7c025a624eefc946cf891acf139050a4359e1"
PLAN = "e321e2956e7c4c6803784e3a72b6d3f565c7063dff221bb6797d66c6e92c02d0"
COST = HERE.parent / "evidence-20261128-r03"
SERVICE = run_path(HERE.parent / "source.py")
CLOCK = run_path(HERE.parent / "replay.py")


class Incumbent:
    def __init__(self, keys):
        self.prim = set(keys)
        self.bank = {}
        self.frequency = defaultdict(int)

    def members(self):
        return self.prim | {layer_id * p.EXPERTS + e for layer_id, e in self.bank}

    def apply(self, layer, expert, old, order):
        key = layer * p.EXPERTS + expert
        p.need(key not in self.prim, "duplicate primary")
        if old >= 0:
            self.prim.remove(layer * p.EXPERTS + old)
        self.prim.add(key)
        hit, _ = s.E["reserve"](self.bank, self.frequency, order, layer, expert, old)
        return not hit


def natural_native(seed):
    frozen = s.E["F"]["unpack"](s.ENTRY / "evidence-entry-20261128-r01/transactions.json.gz")
    suffix, _ = s.E["V"]["sources"]()
    p.need(s.E["digest"](suffix) == frozen["suffix_sha256"], "reservation stream")
    controller = Incumbent(seed)
    for i, (_, _, layer, _, _, expert, old) in enumerate(frozen["prefix"]):
        if layer < p.LAYERS:
            controller.apply(layer, expert, old, i)
    events, initial = [], None
    for i, (call, tile, layer, _, _, expert, old) in enumerate(suffix):
        if call >= 3:
            break
        if call == 2 and initial is None:
            initial = controller.members()
        if layer >= p.LAYERS:
            continue
        before = controller.members() if call == 2 else None
        miss = controller.apply(layer, expert, old, len(frozen["prefix"]) + i)
        if before is not None:
            after = controller.members()
            key = layer * p.EXPERTS + expert
            p.need(after.difference(before) == ({key} if miss else set()), "union admission")
            events.append([i, tile, layer, key, int(miss), sorted(before.difference(after))])
    p.need(sum(r[4] for r in events) == 532 and initial is not None, "call 148 native charge")
    return initial, controller.members(), events, sum(r[4] for r in events)


def replay_supplied(raw, case, keys, source):
    h = run_path(s.QUAL / "warm_residency/replay.py")
    answer = None
    for rep in (2, 3):
        name = f"c294-{case}-{rep}-on"
        stream, _ = h["primary"](raw, name)
        physical, _ = h["boundary"].audit_arm(raw, name)
        controller = Incumbent(keys)
        n = 0
        for i, (phase, tier, key, old) in enumerate(stream):
            if phase != "prefill":
                break
            if tier != "CPU":
                continue
            layer, expert = divmod(key, p.EXPERTS)
            n += controller.apply(layer, expert, -1 if old is None else old % p.EXPERTS, i)
        endpoint = {
            layer_id * p.EXPERTS + e
            for layer_id, members in enumerate(physical[: p.LAYERS])
            for e in members
        }
        p.need(endpoint == controller.prim, "C294 primary before first decode")
        current = set(keys), controller.members(), [], n
        p.need(answer is None or answer == current, "C294 different first decode entry")
        answer = current
    p.need(answer[-1] == source["incumbent"]["prefill_153"], "C294 bank price")
    return answer


def capture(archive, raw):
    inputs = {"natural_nominal": s.natural(archive), **s.supplied(archive)}
    previous = s.SRC["pinned"](
        HERE / "evidence-admission-20261128-r01/decision.json",
        "68850c6f6689652ee2f9a2d27da78279521042014660210740a855b665473448",
    )
    cases = {}
    for name, (prefix, test, seed, published, _) in inputs.items():
        natural = published is None
        preceding = [w for w in test if natural and w.call == 1]
        section = [w for w in test if w.call == (2 if natural else 9)]
        if natural:
            start, end, events, native = natural_native(seed)
        else:
            start, end, events, native = replay_supplied(
                raw, name, published, previous["cases"][name]
            )
        last = {}
        serial = 0
        for w in prefix + preceding:
            for k in w.keys:
                serial += 1
                last[k] = serial
        ordered = sorted(start, key=lambda k: (last.get(k, -1), k))

        def tokens(ws):
            return [[w.call, w.tile, w.layer, w.index, list(w.keys)] for w in ws]

        cases[name] = dict(
            entry=ordered,
            end=sorted(end),
            events=events,
            waves=tokens(section),
            earlier=tokens(preceding),
            native=native,
        )
    return cases


def per_visit(ws, entry, target, transactions):
    members = set(entry)
    grouped = defaultdict(list)
    for row in transactions:
        grouped[tuple(row[1:3])].append(row)
    proof, spare = [], []
    for site, visit in groupby(ws, key=lambda w: (w.tile, w.layer)):
        touched = {k for w in visit for k in w.keys}
        rows = grouped.pop(site, [])
        before = members.copy()
        seen = before.copy()
        paid, extra = [], []
        for i, _, _, key, miss, dropped in rows:
            p.need(
                key in touched and bool(miss) == (key not in members) and set(dropped) <= members,
                "visit native order",
            )
            if miss:
                paid.append(i)
                if key in seen:
                    spare.append([i, key])
                    extra.append(i)
                seen.add(key)
            members.difference_update(dropped)
            members.add(key)
        compulsory = (touched | members) - before
        p.need(compulsory == touched - before and touched <= seen, "unserved native demand")
        p.need(len(compulsory) + len(extra) == len(paid), "visit miss conservation")
        proof.append(dict(site=list(site), native=len(paid), floor=len(compulsory), surplus=extra))
    p.need(not grouped and members == set(target), "final membership")
    return proof, spare


def clocks(spare):
    file = COST / "spans.json.gz"
    p.need(
        s.sha(file) == "1a0a8850446b0c81c018f39f79c258843047958284510115c0086b1fc95e854b",
        "clock witness",
    )
    obs = SERVICE["F"]["unpack"](file)
    native, queue, hits = SERVICE["inputs"]()
    result = {}
    extra = {i for i, _ in spare}
    p.need(not extra & hits, "already credited")
    for tag in ("P97", "P106"):
        for i, key in spare:
            layer, _, _, expert = native[tag]["jobs"][i][0]
            p.need(
                key == p.EXPERTS * layer + expert and native[tag]["jobs"][i][1][0] == 2,
                "PFJ generation",
            )
        rows = []
        for reverse in (False, True):
            nodes, boundaries, _ = CLOCK["build"](
                obs[tag], native[tag], queue[tag], reverse_ties=reverse
            )
            CLOCK["simulate"](obs[tag], nodes, boundaries, set(), set(), control=True)
            old, new = [
                CLOCK["simulate"](obs[tag], nodes, boundaries, jobs, jobs)
                for jobs in (hits, hits | extra)
            ]
            debt = {k: old[k] - new[k] for k in ("first", "valid", "prefill", "decode")}
            p.need(
                debt["decode"] == 0 and debt["first"] == debt["prefill"] == debt["valid"],
                "wrong clock scope",
            )
            rows.append(dict(old=old, proposed=new, saved_ns=debt))
        p.need(rows[0] == rows[1], "worker time tie")
        result[tag] = rows[0]
    return result


def score(witness):
    states = HERE / "plan-admission-20261128-r01/states.json.gz"
    p.need(s.sha(states) == PLAN, "causal frequency state")
    trained = json.loads(gzip.decompress(states.read_bytes()))
    cases = {}
    for name, data in witness.items():
        entry, target = data["entry"], data["end"]
        p.need(
            len(entry) == len(set(entry)) <= 1252 and len(target) == len(set(target)) <= 1252,
            "boundary memberships",
        )
        ws = [p.Wave(*line) for line in data["waves"]]
        obj = ad.Directory.reopen("filter_lru", trained[name]["filter_lru"]["state"])
        for line in data["earlier"]:
            obj.serve(p.Wave(*line))
        obj.bank = dict.fromkeys(entry[-p.CAPACITY :])
        statements, ids = ad.play(obj, ws, lambda _: "prefill")
        loads = statements["prefill"]["reads"]
        repair = len(set(target).difference(obj.bank))
        used = {k for w in ws for k in w.keys}
        absolute = len((set(target) | used).difference(entry))
        future = {k: len(ws) for k in target}
        for i in reversed(range(len(ws))):
            future.update(dict.fromkeys(ws[i].keys, i))
        optimistic_entry = sorted(entry, key=lambda k: (future.get(k, len(ws) + 1), k))[
            : p.CAPACITY
        ]
        oracle, _ = p.ideal(ws, optimistic_entry, p.CAPACITY, lambda _: "prefill", target)
        p.need(absolute <= sum(oracle.values()) <= loads + repair, "lower bound")
        rec = dict(
            entry=len(entry),
            terminal=len(target),
            compulsory_distinct=absolute,
            union=len(used),
            native=data["native"],
            filter_reads=loads,
            filter_restore=repair,
            filter_charged=loads + repair,
            future_reads=oracle["prefill"],
            future_restore=oracle["restore"],
            future_charged=sum(oracle.values()),
            filter_requests_sha256=p.digest(ids),
            dropped_on_entry=max(0, len(entry) - p.CAPACITY),
        )
        if name == "natural_nominal":
            proof, spared = per_visit(ws, entry, target, data["events"])
            p.need(sum(r["native"] for r in proof) == data["native"], "all visits")
            rec.update(visits=proof, dispensable_jobs=spared, clock=clocks(spared))
        cases[name] = rec
    ns = cases["natural_nominal"]["clock"]
    phase = all(r["filter_charged"] < r["native"] for r in cases.values())
    local = all(r["saved_ns"]["first"] > 0 for r in ns.values())
    return dict(
        method=METHOD,
        script=s.sha(Path(__file__)),
        cases=cases,
        evidence="TRACE_DERIVED_CONDITIONAL",
        filter_status="GO_PHASE_FIXTURE" if phase else "NO_GO_PHASE_SWITCH",
        visit_status="GO_VISIT_FIXTURE" if local else "NO_GO_VISIT_REUSE",
        measured_client_ns=None,
        model_forwards=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--new", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--c294-raw", type=Path)
    args = parser.parse_args()
    p.need(s.sha(HERE / "switch-protocol.md") == METHOD, "protocol")
    if args.check:
        compressed = (args.check / "witness.json.gz").read_bytes()
        result = score(json.loads(gzip.decompress(compressed)))
        result["witness_sha256"] = hashlib.sha256(compressed).hexdigest()
        p.need(result == json.loads((args.check / "decision.json").read_bytes()), "public replay")
    else:
        if not (args.archive and args.c294_raw):
            parser.error("--new requires --archive and --c294-raw")
        args.new.mkdir(exist_ok=False)
        try:
            witness = capture(args.archive, args.c294_raw)
            binary = ad.pack(witness)
            result = score(witness)
            result["witness_sha256"] = hashlib.sha256(binary).hexdigest()
            write(args.new / "witness.json.gz", binary)
            write(
                args.new / "decision.json",
                (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(),
            )
        except Exception as exc:
            write(
                args.new / "FAIL.json",
                (json.dumps(dict(error=type(exc).__name__, reason=str(exc))) + "\n").encode(),
            )
            raise
    print(result["filter_status"], result["visit_status"])


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_AS, (900 << 20, 900 << 20))
    main()
