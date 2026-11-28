"""Replay FIFO and worker dependencies on each original PFJ clock."""

import argparse
import gzip
import json
from collections import deque
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
E = run_path(HERE / "entry.py")
H, L, V, F, need, sha = (E[k] for k in ("H", "L", "V", "F", "need", "sha"))
METHOD = "7611b16eb15bbf20308dcf71391b27afd1bc6888f13630d0fc06f4a66512497a"
MIXED = "5c9c4fff78d8b4fdcaacded88b3abc0053a9f7164fc9dedcbc906b2248a3c5d6"
ENTRY = "5e815f588d0aacb559346eeca693311222c2a61d7683b03ede140db275107598"


def queues(archive, service):
    src = F["SRC"]
    prefix = src["Q"]["PROFILE"]
    sample = {}
    for tag, records in service.items():
        name = src["SOURCES"][tag][0]
        arm = archive / ("part-" + tag[1:]) / name / "ON"
        if tag == "P97":
            file = arm / "raw/events.pfj"
            rows, _ = prefix["PFJ"]["read_journal"](file)
        else:
            file = arm / "observer/events.pfj"
            cut, count = prefix["metadata"](file, True)
            rows = prefix["iter_rows"](file, cut, count - cut)
        need(sha(file) == E[tag], "PFJ changed")
        jobs = records["jobs"]
        index = {tuple(j[0]): i for i, j in enumerate(jobs)}
        fifo, useful, skipped = deque(), [], []
        for r in rows:
            if r.kind not in (12, 13, 14, 28):
                continue
            i = index[(r.layer, r.slot, r.gen, r.expert)]
            if r.kind == 12:
                fifo.append((i, r.ns))
                continue
            entry, enq = fifo.popleft()
            need(entry == i and enq <= r.ns, "dequeue without matching FIFO entry")
            if r.kind == 13:
                need(
                    i == len(useful)
                    and (r.worker, r.ns) == (jobs[i][3], jobs[i][4])
                    and jobs[i][2] <= enq,
                    "served enqueue, generation or dispatch",
                )
                useful.append(enq)
            else:
                skipped.append([i, r.kind, r.worker, enq, r.ns])
        need(not fifo and len(useful) == len(jobs), "undrained queues")
        sample[tag] = dict(useful=useful, skipped=skipped)
    return sample


def replay(state, direct, hits, fixed, penalty=0, exempt=-1):
    ready = state["carry_publish_ns"].copy()
    prior = state["previous_dispatch_ns"]
    rows = []
    for j in state["jobs"]:
        worker, expert = j["worker"], j["expert"]
        dispatch = (
            j["dispatch_ns"]
            if fixed
            else max(j["enqueue_ns"], prior, ready[worker]) + j["dispatch_residual_ns"]
        )
        service = j["service_ns"]
        if expert in hits:
            service -= j["read_ns"]
        if expert in direct:
            service -= j["sets_ns"]
        if expert in direct and expert != exempt:
            service += penalty
        need(
            service >= 0 and dispatch >= max(j["enqueue_ns"], prior, ready[worker]),
            "worker or FIFO overlap",
        )
        ready[worker] = dispatch + service
        rows.append([dispatch, ready[worker]])
        prior = dispatch
    last = max(end for _, end in rows)
    result = max(state["barrier_ns"], last) + state["wake_ns"]
    return result, rows


def account(jobs, queue, scenario, bounds):
    times = queue["useful"]
    ids = [j["index"] for j in scenario["jobs"]]
    zero = jobs[ids[0]][2]
    order = sorted(range(len(jobs)), key=lambda i: jobs[i][4])
    offset = order.index(ids[0])
    need(
        order[offset : offset + len(ids)] == ids and set(order[:offset]) == set(range(ids[0])),
        "preceding FIFO cohort",
    )
    issued = order[:offset]
    first, last_claim = jobs[ids[0]][4], jobs[ids[-1]][4]
    skipped = queue["skipped"]
    need(
        all(kind == 14 and 0 <= w < 4 and enq <= pop for _, kind, w, enq, pop in skipped)
        and not any(first <= r[-1] <= last_claim for r in skipped),
        "additional FIFO work overlaps the cohort",
    )
    previous_skips = [r for r in skipped if r[-1] < first]
    prior = max([jobs[i][4] for i in issued] + [r[-1] for r in previous_skips]) - zero
    anchors = [
        max((i for i in issued if jobs[i][3] == w), key=lambda i: jobs[i][-1]) for w in range(4)
    ]
    carry = [jobs[i][-1] - zero for i in anchors]
    for _, _kind, worker, _enq, pop in previous_skips:
        carry[worker] = max(carry[worker], pop - zero)
    active = [i for i in issued if jobs[i][4] <= zero < jobs[i][-1]]
    queued = [i for i in issued if times[i] <= zero < jobs[i][4]]
    need(
        set(active + queued) == {i for i in issued if jobs[i][-1] > zero} and len(active) <= 4,
        "missing inherited job",
    )
    begin, end, last = bounds
    slices = []
    preceding = prior
    ready = carry.copy()
    for i in ids:
        j = jobs[i]
        worker = j[3]
        enq, claim, publication = times[i] - zero, j[4] - zero, j[-1] - zero
        residual = claim - max(enq, preceding, ready[worker])
        reads = j[6] - j[5]
        sets = sum(j[k + 1] - j[k] for k in (7, 9, 11))
        need(
            min(residual, reads, sets) >= 0 and publication - claim > reads + sets,
            "unidentified service",
        )
        slices.append(
            dict(
                index=i,
                expert=j[0][3],
                key=j[0],
                worker=worker,
                enqueue_ns=enq,
                dispatch_ns=claim,
                publish_ns=publication,
                service_ns=publication - claim,
                read_ns=reads,
                sets_ns=sets,
                dispatch_residual_ns=residual,
            )
        )
        preceding, ready[worker] = claim, publication
    peak = max(j["publish_ns"] for j in slices)
    need(
        {tuple(j["key"]) for j in slices if j["publish_ns"] == peak} == {tuple(k) for k in last}
        and begin - zero <= peak <= end - zero,
        "unidentified last publisher",
    )
    state = dict(
        skipped_at_cut=sum(enq <= zero < pop for _, _, _, enq, pop in previous_skips),
        earlier_skip_after_cut=sum(pop > zero for *_, pop in previous_skips),
        total_duplicate_skips=len(skipped),
        earlier_active=active,
        earlier_queued=queued,
        anchor_indices=anchors,
        carry_publish_ns=carry,
        previous_dispatch_ns=prior,
        barrier_ns=begin - zero,
        wake_ns=end - zero - peak,
        jobs=slices,
    )
    original, line = replay(state, set(), set(), False)
    need(
        original == end - zero and line == [[r["dispatch_ns"], r["publish_ns"]] for r in slices],
        "DISK reproduction",
    )
    return state


def prices(state, hits, fixed):
    def run(direct, cached, penalty=0, exempt=-1):
        return replay(state, direct, cached, fixed, penalty, exempt)[0]

    disk, copy, all_id = run(set(), set()), run(set(), hits), run(hits, hits)
    singles = {e: run({e}, hits) for e in sorted(hits)}
    best = min(singles, key=singles.__getitem__)
    advantage = singles[best] - all_id
    need(disk >= copy >= singles[best] >= all_id, "removing service made the last publisher later")
    cap = None
    if not fixed and advantage > 0:
        # Event times are maxima and sums of nondecreasing functions of the surcharge.
        def admitted(p):
            return run(hits, hits, p, best) < singles[best]

        low, high = 0, 1
        while admitted(high):
            high *= 2
            need(high < 1 << 62, "no finite budget")
        while high - low > 1:
            mid = (low + high) // 2
            if admitted(mid):
                low = mid
            else:
                high = mid
        need(admitted(low) and not admitted(low + 1), "non-strict boundary")
        cap = low
    return dict(
        disk_ns=disk,
        copy_ns=copy,
        id_ns=all_id,
        single_ns={str(e): v for e, v in singles.items()},
        best_single=best,
        additional_gain_ns=advantage,
        all_vs_copy_ns=copy - all_id,
        all_vs_disk_ns=disk - all_id,
        max_uniform_extra_ns=cap,
    )


def grade(times, service):
    pin = F["SRC"]["pinned"]
    need(sha(HERE / "queue-protocol.md") == METHOD, "FIFO protocol")
    previous = pin(HERE / "evidence-mixed-20261128-r01/decision.json", MIXED)
    entry = pin(HERE / "evidence-entry-20261128-r01/decision.json", ENTRY)
    cases = pin(H / "evidence-20261128-r01/scenarios.json", E["A"]["PHYSICAL"])
    threshold = max(
        abs(r["comparisons"]["best_ONE_minus_ALL"]["median_ns"])
        for arm in previous["arms"].values()
        for r in arm["directions"]
    )
    result = {}
    for tag, native in service.items():
        need(
            len(times[tag]["useful"]) == len(native["jobs"]) == 2354
            and times[tag]["useful"] == sorted(times[tag]["useful"]),
            "incomplete enqueue journal",
        )
        barriers = {tuple(s): (b, e, last) for s, b, e, last in native["last"]}
        result[tag] = {}
        for name, case in cases[tag].items():
            state = account(native["jobs"], times[tag], case, barriers[tuple(case["site"])])
            hits = set(entry["journals"][tag]["registered"][name]["expert"])
            result[tag][name] = dict(
                state=state,
                observed_hits=sorted(hits),
                fixed_dispatch=prices(state, hits, True),
                dependency_dispatch=prices(state, hits, False),
            )
    gains = [v["prefill9"]["dependency_dispatch"]["additional_gain_ns"] for v in result.values()]
    label = (
        "GO_FIFO_FIXTURE"
        if min(gains) > threshold
        else ("NO_GO_FIFO_EXTENSION" if max(gains) <= threshold else "INCONCLUSIVE_FIFO_EXTENSION")
    )
    return dict(
        status=label,
        journals=result,
        required_ns=threshold,
        method_sha256=METHOD,
        evidence="TRACE_DERIVED_FIXED_RESOURCES_AND_SERVICE",
        enqueues_sha256=E["digest"](times),
        model_forwards=0,
        weight_bytes_read=0,
        measured_client_gain_ns=None,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path)
    mode.add_argument("--new-output-dir", type=Path)
    p.add_argument("--archive", type=Path)
    a = p.parse_args()
    out = a.new_output_dir
    if out and not a.archive:
        p.error("raw PFJ directory required")
    if out:
        out.mkdir(mode=0o700)
    try:
        f = L["X"]["ORIGINAL"] / "service.json.gz"
        need(sha(f) == V["SERVICE"], "unverified worker service")
        service = F["unpack"](f)
        times = (
            queues(a.archive, service) if a.archive else F["unpack"](a.check / "enqueues.json.gz")
        )
        result = grade(times, service)
        if out:
            with (out / "enqueues.json.gz").open("xb") as stream:
                stream.write(gzip.compress(L["encode"](times), mtime=0))
            t = out / ".pending"
            t.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            t.rename(out / "decision.json")
        else:
            need(
                result == json.loads((a.check / "decision.json").read_bytes())
                and gzip.decompress((a.check / "enqueues.json.gz").read_bytes())
                == L["encode"](times),
                "published FIFO recurrence",
            )
        print(
            result["status"],
            {
                tag: v["prefill9"]["dependency_dispatch"]["additional_gain_ns"]
                for tag, v in result["journals"].items()
            },
        )
    except Exception as exc:
        if out:
            (out / "FAIL.json").write_text(json.dumps(dict(error=repr(exc))) + "\n")
        raise


if __name__ == "__main__":
    main()
