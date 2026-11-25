"""Reconcile the host callbacks of the natural 2044+153 C281 turn, preserving the worker clock."""

import argparse
import hashlib
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PFJ = run_path(str(HERE.parents[4] / "phase_fd/integrated/analyse.py"))
check, identity, union_ns = PFJ["check"], PFJ["identity"], PFJ["union_ns"]
GEOMETRY = [[5], [32, 32, 32, 32, 20]] + [[1] for _ in range(46)]
HISTORICAL = "1a96cca8af0fd2dd0a4e4fd1ba2afc031320e6ff0be9b335cead5f5e0035f018"


def read(path):
    return json.loads(path.read_bytes())


def verify_routes(site_rows, demands, masks, calls):
    digest = hashlib.sha256()
    total = 0
    expected_sites = set()
    for number, call in enumerate(calls, 1):
        for tile, (tokens, pos, _) in enumerate(call["geometry"], 1):
            for layer in range(36):
                site = (number, tile, layer)
                ranks = site_rows.get(site, [])
                expected = (
                    tokens if layer < 35 else int(number > 1 and tile == len(call["geometry"]))
                )
                check(len(ranks) == expected, "routed rows differ from the target output mask")
                if site in masks:
                    expected_sites.add(site)
                    check(masks[site] == expected, "remap rank coverage")
                check(expected == 0 or site in masks, "missing layer")
                group = demands.get(site, [])
                check(len(group) == len(set(group)), "expert demanded in multiple waves")
                check(set(group) == {v for rank in ranks for v in rank}, "top-k versus service")
                for i, rank in enumerate(ranks):
                    position = pos + (i if layer < 35 else tokens - 1)
                    digest.update(struct.pack("<5i4B", number, tile, layer, position, i, *rank))
                    total += 1
    check(set(masks) == expected_sites and set(site_rows) <= expected_sites, "foreign routed site")
    return {"rows": total, "sha256": digest.hexdigest()}


def close_barrier(e, site, required, slots, last_publish, barrier, blocking):
    start, waiting, unresolved = barrier
    check(
        site == (e.call, e.tile, e.layer, e.wave) and e.a == waiting and start <= e.ns,
        "consumer barrier return",
    )
    check(all(slots[(k[0], k[1])] == (k, 2) for k in required), "demand not ready at resume")
    if unresolved:
        check(waiting, "unreported waiter")
        pub = max(last_publish[k] for k in unresolved)
        check(start <= pub <= e.ns, "publication outside the waiting interval")
        blocking["wait_to_last_publication_ns"] += pub - start
        blocking["last_publication_to_resume_ns"] += e.ns - pub
        blocking["barriers_with_pending_generation"] += 1


def host_trace(rows):
    slots, last_publish = {}, {}
    calls, ranks, demands, masks = [], defaultdict(list), defaultdict(list), {}
    callbacks, waits = [], []
    call = tile = site = barrier = victim = remap_start = None
    next_position = 2044
    required, blocking, handoff = [], Counter(), None
    for e in rows:
        if e.kind == 1:
            check(call is None and e.call == len(calls) + 1 <= len(GEOMETRY), "call order")
            g = GEOMETRY[e.call - 1]
            check(
                e.a == sum(g)
                and (e.b, e.c) in ((-1, -1), (next_position, next_position + sum(g) - 1)),
                "input span",
            )
            call = {"number": e.call, "enter_ns": e.ns, "geometry": []}
            calls.append(call)
            if e.call == 3:
                h = hashlib.sha256()
                for (layer, s), (k, state) in sorted(slots.items()):
                    h.update(struct.pack("<5q", layer, s, k[3], k[2], state))
                handoff = {
                    "sha256": h.hexdigest(),
                    "slot_states": dict(Counter(st for _, st in slots.values())),
                }
        elif e.kind == 2:
            check(
                call and e.call == call["number"] and tile is site is None and e.a == 0,
                "external return",
            )
            check([x[0] for x in call["geometry"]] == GEOMETRY[e.call - 1], "incomplete call")
            call.update(return_ns=e.ns, queued=e.b, claimed=e.c)
            call = None
        elif e.kind == 3:
            check(call and call["number"] == e.call and tile is None, "tile lineage")
            check(
                e.tile == len(call["geometry"]) + 1 and e.tile <= len(GEOMETRY[e.call - 1]),
                "tile order",
            )
            check(
                (e.a, e.b, e.c)
                == (GEOMETRY[e.call - 1][e.tile - 1], next_position, next_position + e.a - 1),
                "tile positions",
            )
            next_position += e.a
            tile = (e.call, e.tile)
            call["geometry"].append((e.a, e.b, e.c))
        elif e.kind == 4:
            check(tile == (e.call, e.tile) and site is None and e.a == 0, "tile completion")
            tile = None
        elif e.kind == 5:
            key = identity(e)
            check(
                e.call == 1
                and e.layer in range(36)
                and e.slot in range(40)
                and (e.layer, e.slot) not in slots
                and e.a in (0, 1, 2),
                "initial slot",
            )
            slots[(e.layer, e.slot)] = key, e.a
        elif e.kind == 9:
            check(
                site is None
                and tile == (e.call, e.tile)
                and e.layer in range(36)
                and e.b == 4
                and e.a >= 0,
                "remap scope",
            )
            site = (e.call, e.tile, e.layer, e.wave)
            if e.wave in (-1, 0):
                check(site[:3] not in masks, "duplicate first wave")
                masks[site[:3]] = e.a
            required, remap_start = [], e.ns
        elif e.kind == 27:
            check(
                site == (e.call, e.tile, e.layer, e.wave)
                and e.wave in (0, -1)
                and e.b == len(ranks[site[:3]])
                and 0 <= e.a < 2**32,
                "rank lineage",
            )
            rank = tuple(e.a.to_bytes(4, "little"))
            check(max(rank) < 128 and len(set(rank)) == 4, "invalid routed expert")
            ranks[site[:3]].append(rank)
        elif e.kind in (10, 11, 17):
            k = identity(e)
            loc = (e.layer, e.slot)
            old, state = slots[loc]
            if e.kind == 11:
                check(
                    site == (e.call, e.tile, e.layer, e.wave)
                    and old[2] + 1 == e.gen
                    and old[3] == e.a
                    and state != 1
                    and old not in required,
                    "reservation lineage",
                )
                slots[loc] = k, 1
            elif e.kind == 17:
                check((old, state) == (k, 1) and k not in last_publish, "publication lineage")
                slots[loc] = k, 2
                last_publish[k] = e.ns
            else:
                check(
                    site == (e.call, e.tile, e.layer, e.wave)
                    and old == k
                    and state in (1, 2)
                    and k not in required,
                    "demand generation",
                )
                demands[site[:3]].append(e.expert)
                required.append(k)
        elif e.kind == 19:
            check(
                site == (e.call, e.tile, e.layer, e.wave) and barrier is None and e.a in (0, 1),
                "nested/unbound barrier",
            )
            unresolved = [k for k in required if slots[(k[0], k[1])][1] == 1]
            barrier = e.ns, e.a, unresolved
        elif e.kind == 20:
            check(barrier is not None, "missing barrier entry")
            close_barrier(e, site, required, slots, last_publish, barrier, blocking)
            if e.a:
                waits.append((e.call, barrier[0], e.ns))
            barrier = None
        elif e.kind == 21:
            check(site == (e.call, e.tile, e.layer, e.wave) and victim is None, "victim wait")
            victim = e.ns
        elif e.kind == 22:
            check(site == (e.call, e.tile, e.layer, e.wave) and victim is not None, "victim wake")
            waits.append((e.call, victim, e.ns))
            victim = None
        elif e.kind == 23:
            check(
                site == (e.call, e.tile, e.layer, e.wave) and barrier is victim is None,
                "remap return",
            )
            callbacks.append((e.call, remap_start, e.ns))
            site = remap_start = None
    check(
        len(calls) == 48
        and call is tile is site is None
        and len(slots) == 1440
        and next_position == 2243
        and handoff,
        "incomplete natural geometry",
    )
    for previous, following in zip(calls, calls[1:], strict=False):
        check(previous["enter_ns"] <= previous["return_ns"] <= following["enter_ns"], "call clock")
    check(calls[-1]["return_ns"] >= calls[-1]["enter_ns"], "last return")
    route = verify_routes(ranks, demands, masks, calls)
    return {
        "calls": calls,
        "route": route,
        "first_decode": handoff,
        "blocking": dict(blocking),
        "callback_spans": callbacks,
        "wait_spans": waits,
    }


def bound(host, full, public):
    call = host["calls"]
    phase = public["prefill_s"]
    decode = public["decode_s"]
    first = public["first_final_s"]
    start = full["request_started_monotonic"]
    check(
        full["accepted"]
        and full["timings"]["cache_n"] == 2044
        and (full["timings"]["prompt_n"], full["timings"]["predicted_n"]) == (153, 47),
        "T2 work",
    )
    check(
        abs(full["timings"]["prompt_ms"] / 1000 - phase) < 1e-6
        and abs(full["timings"]["predicted_ms"] / 1000 - decode) < 1e-6
        and abs(full["stream_metrics"]["first_final_content_chunk_s"] - first) < 1e-6,
        "native and client prices",
    )
    check(
        math.floor(start * 1e9) <= call[0]["enter_ns"] < (start + first) * 1e9
        and call[-1]["return_ns"] <= math.ceil(full["request_ended_monotonic"] * 1e9) + 1_000_000,
        "client scope",
    )
    cuts = {}
    for key in ("callback_spans", "wait_spans"):
        prompt = union_ns([(a, b) for c, a, b in host[key] if c <= 2])
        generation = union_ns([(a, b) for c, a, b in host[key] if c > 2])
        first_cut = math.ceil((start + first) * 1e9)
        until = union_ns([(a, min(b, first_cut)) for _, a, b in host[key] if a < first_cut])
        cuts[key] = {"prefill_ns": prompt, "decode_ns": generation, "through_first_final_ns": until}
    margins = {}
    for rate in (6, 8, 10):
        # Concede the complete decode saving before the first final, with unchanged tail.
        credit = max(0, decode - 47 / rate)
        need_ns = math.floor(max(0, first - 10 - credit) * 1e9)
        upper = cuts["callback_spans"]["prefill_ns"]
        margins[str(rate)] = {
            "required_prefill_saving_ns": need_ns,
            "free_remap_ns": upper,
            "decision": "NO_GO_FIXED_EXTERIOR" if upper < need_ns else "HEADROOM_ONLY",
        }
    return {
        "observed_s": {"prefill": phase, "decode": decode, "first_final": first},
        "host_unions": cuts,
        "scenarios": margins,
        "independent_last_cuda_consumer": "UNKNOWN",
    }


def audit_arm(arm_dir, receipt, trigger_ns):
    audit_jobs = run_path(str(HERE / "jobs.py"))["audit_jobs"]

    arm_dir = Path(arm_dir)
    rows, header = PFJ["read_journal"](arm_dir / "raw/events.pfj")
    identity_stats = receipt["transport"]["data_stat"]
    work = audit_jobs(rows, identity_stats["pack"], identity_stats["model"])
    counts = work["counts"]
    check(
        not (
            counts["retries_eintr"]
            or counts["read_errors"]
            or counts["short_payload"]
            or work["failed_jobs"]
            or work["cancelled_keys"]
            or counts["final_load_failed"]
        ),
        "producer retried, failed or cancelled",
    )
    host = host_trace(rows)
    check(trigger_ns < host["calls"][0]["enter_ns"], "observed before T2 trigger")
    reference = read(HERE / "historical.json")
    check(host["route"] == reference["route"], "logical target route diverged")
    totals = bound(host, read(arm_dir / "raw/T2-result.json"), receipt["rows"][1])
    if work["status"] != "COMPLETE":
        totals["scenarios"] = {}
        totals["withheld_reason"] = "INCOMPLETE_SERVICE_AT_CAPTURE_BOUNDARY"
    return {
        "status": "PASS_PACK_NATURAL_TRACE"
        if work["status"] == "COMPLETE"
        else "INCOMPLETE_PACK_NATURAL_TRACE",
        "header": header,
        "route": host["route"],
        "jobs": work,
        "first_decode": host["first_decode"],
        "blocking": host["blocking"],
        "coverage": {
            "logical_routes": "ORDERED_TOP4_AT_REMAP",
            "physical_demand": "EXPERT_SLOT_GENERATION_BY_WAVE",
            "effective_per_token_parking_mask": "UNOBSERVED",
            "last_cuda_reader": "BOUNDED_ONLY_BY_EXISTING_DOWNSTREAM_DEPENDENCIES",
            "temporal_claim": "FIXED_EXTERIOR_SCENARIO_ONLY",
        },
        "calls": host["calls"],
        "budget": totals,
    }


def historical(arm):
    pins = {
        "receipt.json": "78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43",
        "raw/T2-result.json": "7d73bedd1a6e801655a4680ace7cc7a0e08a931e9b93e72fdfc7f15126211569",
        "raw/events.pfj": HISTORICAL,
    }
    for path, expected in pins.items():
        check(hashlib.sha256((arm / path).read_bytes()).hexdigest() == expected, "C269 " + path)
    rows, header = PFJ["read_journal"](arm / "raw/events.pfj")
    host = host_trace(rows)
    now = bound(host, read(arm / "raw/T2-result.json"), read(arm / "receipt.json")["rows"][1])
    return {
        "source": "C269_NATIVE_T2_REFERENCE",
        "journal_sha256": header["journal_sha256"],
        "inputs": pins,
        "route": host["route"],
        "fixed_remainder": now,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reproduce the independent C269 natural-turn reference"
    )
    parser.add_argument("historical_arm", type=Path)
    args = parser.parse_args()
    print(json.dumps(historical(args.historical_arm), indent=2, sort_keys=True))
