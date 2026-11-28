"""Bound the last CPU reader of every overwritten frame on each native request clock."""

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SAMPLING = (
    HERE.parents[1] / "verifier_wait/forecast/retention/eviction/late_owner/contention/sampling"
)
FRAMES = run_path(SAMPLING / "frames.py")
F, V, X, need, sha = (FRAMES[k] for k in ("F", "V", "X", "need", "sha"))
REGISTERED = "5f916b0c3d7af35f28eac2166b4aa75be6086589c283e290c66048a28789b28c"
PARENT = "7d41b3084e0051ffba6f5c65bef34b6cdd1dae0ddf89f63ef3af2acf826a7e95"
PHASES = ("prefill_5", "prefill_148", "decode_to_first", "tail")


def phase(call):
    if call <= 2:
        return PHASES[call - 1]
    return PHASES[2] if call <= 46 else PHASES[3]


def encode(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def inputs():
    need(sha(HERE / "lifetime-protocol.md") == REGISTERED, "registered protocol")
    prior = F["SRC"]["pinned"](SAMPLING / "evidence-frames-20261128-r01/frames.json", PARENT)
    need(FRAMES["evaluate"]() == prior, "ownership, entry into decode, and producer clocks")
    tx, effects = V["sources"]()
    service = X["ORIGINAL"] / "service.json.gz"
    need(sha(service) == V["SERVICE"], "native clocks and ordered reservations")
    source = F["unpack"](V["TIER"] / "evidence-tier-20261128-r01/transactions.json.gz")
    initial = {
        (layer, slot_id): (layer, slot_id, generation, expert)
        for layer, slot_id, expert, generation in source["initial"]
        if layer < 25
    }
    primary, bank = list(range(1000)), list(range(1000, 1252))
    writes, actions, rows = {}, {}, []
    for i, ((_, _, layer, slot_id, *_), (tier, src, dst)) in enumerate(
        zip(tx, effects, strict=True)
    ):
        if layer >= 25:
            continue
        need(tier == 0, "CPU reservation assigned to another tier")
        slot = 40 * layer + slot_id
        victim = primary[slot]
        victim_writer = writes.get(victim) if dst is not None else None
        FRAMES["rebind"](primary, bank, slot, src, dst)
        frame = primary[slot]
        previous = writes.get(frame)
        hit = src is not None
        actions[i] = (frame, previous, hit)
        if not hit:
            writes[frame] = i
        rows.append((i, frame, hit, previous, victim, victim_writer))
    need(V["C"]["IV"]["digest"](rows) == prior["ordered_actions_sha256"], "physical action order")
    return initial, tx, actions, F["unpack"](service), prior


def reopen(archive, service, initial):
    basis, _, _ = F["freeze"]()
    out = {}
    for tag, native in service.items():
        name, outer, _ = F["SRC"]["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P106":
            pfj = root / "ON/observer/events.pfj"
            _, rows, _, _ = F["SRC"]["Q"]["read_new"](root, outer)
        else:
            pfj = root / "ON/raw/events.pfj"
            F["SRC"]["pinned"](root / "family.json", outer)
            rows, _ = F["SRC"]["T"]["PFJ"]["read_journal"](pfj)
        journal = sha(pfj)
        need(journal == basis["arms"][tag]["journal_sha256"], "closed original journal")
        snapshot = {
            (r.layer, r.slot): F["SRC"]["key"](r) for r in rows if r.kind == 5 and r.layer < 25
        }
        need(len(initial) == 1000 and snapshot == initial, "all initial primary generations")
        need(F["collect"](rows) == native, "all jobs, generations, barriers and worker service")
        waves, _ = F["SRC"]["timeline"](rows)
        cpu = [[w.site, w.start, w.end, sorted(w.demands)] for w in waves if w.site[2] < 25]
        need(rows[-1].kind == 25 and rows[-1].ns >= cpu[-1][2], "terminal marker")
        out[tag] = dict(journal_sha256=journal, bytes=pfj.stat().st_size, cpu=cpu, end=rows[-1].ns)
    return out


def exposure(lower, upper, write):
    """Bounds on the delay of one producer until the final use of the old physical epoch."""
    need(lower <= upper, "inverted last-reader bounds")
    if write >= upper:
        return "safe", 0, 0
    if write < lower:
        return "unavoidable", lower - write, upper - write
    return "possible", 0, upper - write


def price_write(leases, frame, previous_writer, when):
    last = leases.get((frame, previous_writer))
    return exposure(last[0], last[1], when) if last else ("no_observed_reader", 0, 0)


def grade_arm(observed, native, initial, tx, actions):
    jobs = native["jobs"]
    by_site = defaultdict(list)
    for i in actions:
        key, site = jobs[i][:2]
        call, tile, layer, slot_id, generation, expert, _ = tx[i]
        need(
            key == [layer, slot_id, generation, expert] and site[:3] == [call, tile, layer],
            "native generation",
        )
        by_site[tuple(site)].append(i)
    # An epoch belongs to the physical frame. A promotion can change both layer and slot.
    slots = {slot: (key, 40 * slot[0] + slot[1], None) for slot, key in initial.items()}
    old_readers = {}
    promoted = {}
    consumed = set()
    info = {p: Counter() for p in PHASES}
    hist = {p: Counter() for p in PHASES}
    cohorts = {}
    witness = None
    cpu = observed["cpu"]
    checked = []
    previous_end = 0
    for j, (site, start, end, demands) in enumerate(cpu):
        upper = cpu[j + 1][1] if j + 1 < len(cpu) else observed["end"]
        layer = site[2]
        need(layer in range(25) and previous_end <= start < end <= upper, "serial CPU envelopes")
        previous_end = end
        p = phase(site[0])
        count = info[p]
        arrivals = by_site.pop(tuple(site), [])
        for i in arrivals:
            key = tuple(jobs[i][0])
            f, prior_writer, hit = actions[i]
            old, _, _ = slots[key[:2]]
            need(
                start <= jobs[i][2] <= end and (key[2] - 1, tx[i][6]) == old[2:],
                "generation change within callback",
            )
            if hit:
                promoted[key] = i
            slots[key[:2]] = key, f, prior_writer if hit else i
            checked.append(i)
        first = []
        for demand in demands:
            key = tuple(demand)
            current, frame, writer = slots[key[:2]]
            need(key == current and key[0] == layer, "consumer reached a stale generation")
            old_readers[frame, writer] = (end, upper, site, key)
            if key in promoted and key not in consumed:
                consumed.add(key)
                first.append(promoted[key])
        count.update(
            callbacks=1,
            active_callbacks=int(bool(demands)),
            demand_generations=len(demands),
            promotions=sum(actions[i][2] for i in arrivals),
            first_uses=len(first),
        )
        if demands:
            hist[p][str(len(first))] += 1
        if len(first) >= 2:
            count.update(grouped_callbacks=1, grouped_promotions=len(first))
            # One actual site for each group size and phase, with its global reservation indexes.
            cohorts.setdefault((p, len(first)), [site, sorted(first), len(demands)])
    need(checked == list(actions) and not by_site, "reservation coverage")
    keys = ("reservation", "pack_read", "first_set")
    clocks = {p: {k: Counter() for k in keys} for p in PHASES}
    worst = {k: None for k in keys}
    for i, (f, previous, hit) in actions.items():
        if hit:
            continue
        job = jobs[i]
        p = phase(job[1][0])
        info[p].update(writes=1, old_frame_without_in_window_writer=int(previous is None))
        readers = old_readers.get((f, previous))
        for name, time in zip(keys, (job[2], job[5], job[7]), strict=True):
            costs = clocks[p][name]
            kind, lo, hi = price_write(old_readers, f, previous, time)
            costs[kind] += 1
            if readers is None:
                continue
            costs.update(lower_worker_ns=lo, upper_worker_ns=hi)
            slack = time - readers[1]
            if worst[name] is None or slack < worst[name]["upper_slack_ns"]:
                worst[name] = dict(reservation_index=i, frame=f, upper_slack_ns=slack)
        if witness is None and readers is not None and readers[1] - readers[0] >= 2:
            lo, hi, site, reader_key = readers
            probes = [
                price_write(old_readers, f, previous, t) for t in (lo - 1, (hi + lo) // 2, hi)
            ]
            need(
                [r[0] for r in probes] == ["unavoidable", "possible", "safe"]
                and probes[0][1] == 1
                and probes[-1][2] == 0,
                "mutant overwrote the wrong physical epoch",
            )
            witness = dict(
                reservation_index=i,
                reader=list(reader_key),
                site=site,
                frame=f,
                previous_writer=previous,
                range_ns=[lo, hi],
                classifications=[v[0] for v in probes],
            )
    need(witness is not None, "missing observed physical conflict control")
    missing = sorted(promoted[k] for k in promoted.keys() - consumed)
    need(
        len(promoted) == 469
        and sum(c["writes"] for c in info.values()) == 1125
        and len(promoted) == sum(c["first_uses"] for c in info.values()) + len(missing),
        "unaccounted promotion or write",
    )
    for p, c in info.items():
        need(sum(hist[p].values()) == c["active_callbacks"], "first-use histogram")
        for counts in clocks[p].values():
            need(
                sum(counts[k] for k in ("no_observed_reader", "safe", "possible", "unavoidable"))
                == c["writes"],
                "write conservation",
            )
    return dict(
        journal_sha256=observed["journal_sha256"],
        raw_B=observed["bytes"],
        phases=info,
        first_uses_per_active_wave=hist,
        unread_promotions=missing,
        groups=[dict(phase=p, promotions=n, sample=a) for (p, n), a in sorted(cohorts.items())],
        overwrite_clocks=clocks,
        least_slack=worst,
        fault_witness=witness,
    )


def grade(windows, args):
    initial, tx, actions, service, parent = args
    basis, _, _ = F["freeze"]()
    need(set(windows) == set(service) == {"P97", "P106"}, "both original observations")
    for tag, w in windows.items():
        need(w["journal_sha256"] == basis["arms"][tag]["journal_sha256"], "journal identity")
    arms = {tag: grade_arm(w, service[tag], initial, tx, actions) for tag, w in windows.items()}
    a, b = arms.values()
    for key in ("phases", "first_uses_per_active_wave", "unread_promotions", "groups"):
        need(a[key] == b[key], "same logical workload across the two clocks")
    costs = [
        c for arm in arms.values() for p in arm["overwrite_clocks"].values() for c in p.values()
    ]
    if any(c["unavoidable"] for c in costs):
        verdict = "NO_GO_UNPROTECTED"
    elif any(c["possible"] for c in costs):
        verdict = "INCONCLUSIVE_LAST_READER"
    else:
        verdict = "NO_POSSIBLE_CONFLICT_ON_OBSERVED_CPU_SCHEDULE"
    grouped = any(a["phases"][p]["grouped_callbacks"] for p in PHASES[:3])
    return dict(
        protocol_sha256=REGISTERED,
        frame_action_digest=parent["ordered_actions_sha256"],
        entry_decode_state=parent["entry_decode_state"],
        journals=arms,
        last_reader=verdict,
        groups="GO_GROUP_FIXTURE" if grouped else "NO_GO_GROUP_FIXTURE",
        evidence="TRACE_DERIVED_SERIAL_CPU",
        changed_schedule="UNMEASURED",
        model_forwards=0,
        HTTP_requests=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-archive", type=Path)
    dest = parser.add_mutually_exclusive_group(required=True)
    dest.add_argument("--new-output-dir", type=Path)
    dest.add_argument("--check", type=Path)
    a = parser.parse_args()
    os.umask(0o077)
    if not a.new_output_dir:
        out = a.check
    else:
        need(a.raw_archive is not None, "creation requires both original journals")
        out = a.new_output_dir
        out.mkdir()
    try:
        args = inputs()
        compact = out / "waves.json.gz"
        if a.raw_archive is not None:
            raw = encode(reopen(a.raw_archive, args[3], args[0]))
            if a.check:
                need(gzip.decompress(compact.read_bytes()) == raw, "original journal projection")
            else:
                compact.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
        decision = grade(json.loads(gzip.decompress(compact.read_bytes())), args)
        decision["compressed_windows_sha256"] = hashlib.sha256(compact.read_bytes()).hexdigest()
        if a.check:
            need(decision == json.loads((out / "decision.json").read_bytes()), "published decision")
        else:
            (out / "decision.json").write_text(
                json.dumps(decision, indent=2, sort_keys=True) + "\n"
            )
        print(decision["last_reader"], decision["groups"])
    except Exception as exc:
        if a.new_output_dir:
            (out / "FAIL.json").write_text(json.dumps({"error": repr(exc)}) + "\n")
        raise


if __name__ == "__main__":
    main()
