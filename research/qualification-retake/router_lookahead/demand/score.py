"""Join calibrated C270 activations with the numerically identical C292 worker journal."""

import argparse
import json
import os
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
TF = run_path(HERE.parent / "tf32/score.py")
P = TF["P"]
need = P.need
NATIVE = HERE.parents[1] / "igpu_resident_rank/request_budget/device/pack_native"
AUDIT = run_path(NATIVE / "audit.py")
JOURNAL = "d913ac7abae783fa4bed96ed7e292151a84d0b765eefb3c90c3496c689a07bb2"
CAL = "edaea21eeca1913f2734cd1b790a83d1b27ab23c1a6a8074bd0345efdc14b64c"
METHOD = "b2979b21bc6717514797758e9850853e6af007254f7dc2ce0d5a26c5f428ec39"


def choose(rows, occupied, limit):
    counts = Counter(int(expert) for row in rows for expert in row)
    eligible = sorted(counts.keys() - occupied, key=lambda key: (-counts[key], key))
    return eligible[:limit], len(counts.keys() & occupied)


def journal(events):
    slots, cuts, tiles, ends, starts = {}, {}, {}, {}, {}
    routes, jobs, demands, bysite = (defaultdict(list) for _ in range(4))
    worker_ids = set()
    for i, r in enumerate(events):
        tile, site = (r.call, r.tile), (r.call, r.tile, r.layer)
        physical, identity = (r.layer, r.slot), AUDIT["identity"](r)
        if r.kind == 3:
            need(tile not in tiles and r.c == r.b + r.a - 1, "tile position")
            tiles[tile] = (r.b, r.c)
        elif r.kind == 5:
            need(physical not in slots and (r.a, r.gen, r.expert) == (0, 0, -1), "cold entry")
            slots[physical] = (r.gen, r.expert)
        elif r.kind == 9:
            starts.setdefault(site, (i, r.ns, r.wave))
        elif r.kind == 27:
            q = tuple(r.a.to_bytes(4, "little"))
            need(r.b == len(routes[site]) and len(set(q)) == 4 and max(q) < 128, "rank IDs")
            routes[site].append(q)
        elif r.kind == 11:
            need(
                slots[physical] == (r.gen - 1, r.a) and not jobs[identity],
                "eviction/generation",
            )
            slots[physical] = (r.gen, r.expert)
            jobs[identity].append(r)
            bysite[site].append((i, identity, r.wave, r.ns))
        elif r.kind == 10:
            need(slots[physical] == (r.gen, r.expert), "authoritative demand generation")
            demands[site].append(identity)
        elif r.kind in (13, 30, 16, 17):
            need(r.worker in range(4), "worker")
            jobs[identity].append(r)
            worker_ids.add(r.worker)
        elif r.kind == 23:
            ends[site] = i, r.ns
            if r.layer < 35:
                target = (*tile, r.layer + 1)
                cuts[target] = (i, r.ns, {slots[r.layer + 1, j][1] for j in range(40)} - {-1})
    need(len(tiles) == 38 and len(slots) == 1440 and worker_ids == set(range(4)), "population")
    need(len(jobs) == 4501, "job count")
    for job in jobs.values():
        need([r.kind for r in job] == [11, 13, 30, 16, 16, 16, 17], "worker history")
        need(len({r.worker for r in job[1:]}) == 1, "single owner")
        read = job[2]
        need(read.b == read.c == AUDIT["WINDOW"] and not read.error, "read size")
        need(read.a == (read.layer * 128 + read.expert) * AUDIT["STRIDE"], "pack address")
        need([r.component for r in job[3:6]] == [0, 1, 2], "SET order")
        for r in job[3:6]:
            need((r.a, r.b, r.c) == (AUDIT["SLAB"], r.slot * r.a, r.component * r.a), "SET address")
    return tiles, starts, ends, cuts, routes, demands, bysite


def classify(proposals, routed, eligible_jobs, first_wave):
    # A unique offer can cover only the earliest demanded generation at this destination.
    hit = set(proposals) & eligible_jobs.keys()
    return Counter(
        sites=1,
        offers=len(proposals),
        jobs_hit=len(hit),
        hit_first_wave=sum(eligible_jobs[key][0][0] == first_wave for key in hit),
        hit_later_wave=sum(eligible_jobs[key][0][0] != first_wave for key in hit),
        offered_routed_without_job=len((set(proposals) & routed) - hit),
        offered_unused=len(set(proposals) - routed),
        eligible_keys=len(eligible_jobs),
        eligible_jobs=sum(map(len, eligible_jobs.values())),
    )


def score(events, rows, params):
    tiles, starts, ends, cuts, routes, demands, bysite = journal(events)
    positions = {v[0]: k for k, v in tiles.items()}
    previous = dict(zip(list(tiles)[1:], list(tiles)[:-1], strict=True))
    result, gaps, until_reserve = defaultdict(Counter), defaultdict(list), defaultdict(list)
    matched = 0
    for (phase, layer), record in sorted(rows.items()):
        tile = positions[P.PHASES[phase][0]]
        site = (*tile, layer)
        truth = record["ffn_moe_topk"].tolist()
        need(truth == list(map(list, routes[site])), "same-position ordered ranks")
        matched += len(truth)
        if not layer:
            continue
        source = rows[phase, layer - 1]
        offset = record["start"] - source["start"]
        need(offset >= 0 and record["start"] + len(truth) - 1 <= tiles[tile][1], "output mask")
        x = source["attn_post_norm"][offset : offset + len(truth)]
        pred = P.infer(x, params[layer - 1][0], params[layer])
        previous_ranks = routes.get((*previous[tile], layer)) if tile in previous else None
        ix, release, occupied = cuts[site]
        first, first_ns, wave = starts[site]
        end, _ = ends[site]
        need(ix < first <= end and release < first_ns, "source before target")
        routed = {v for row in truth for v in row}
        demand_ids = set(demands[site])
        need(routed == {key[-1] for key in demand_ids}, "ranks to physical demands")
        eligible_jobs = defaultdict(list)
        for j, key, w, ns in bysite[site]:
            need(first < j < end and ns >= release, "reservation site or clock")
            if key[-1] not in occupied and key in demand_ids:
                eligible_jobs[key[-1]].append((w, ns))
        group = ("prefill" if phase.startswith("prefill") else "decode") + (
            "/CPU" if layer < 25 else "/CUDA"
        )
        gaps[group].append(first_ns - release)
        policies = [("projection", pred)]
        if previous_ranks:
            policies += [("projection_paired", pred), ("previous_target", previous_ranks)]
        for label, offered_rows in policies:
            for size in (4, None):
                offered, filtered = choose(offered_rows, occupied, size)
                cell = f"{group}/{label}/" + ("four" if size else "union")
                counts = classify(offered, routed, eligible_jobs, wave)
                counts.update(filtered_resident=filtered)
                result[cell].update(counts)
                until_reserve[cell].extend(
                    eligible_jobs[k][0][1] - release for k in offered if k in eligible_jobs
                )
    need(matched == 3400, "rank bridge coverage")
    for c in result.values():
        need(
            c["offers"] == c["jobs_hit"] + c["offered_routed_without_job"] + c["offered_unused"],
            "offer conservation",
        )
        need(c["jobs_hit"] == c["hit_first_wave"] + c["hit_later_wave"], "generation conservation")

    def distribution(v):
        return (
            {"count": len(v), "min": min(v), "median": statistics.median(v), "max": max(v)}
            if v
            else {"count": 0}
        )

    return dict(
        matching_ordered_quartets=matched,
        counts=result,
        cut_to_first_remap_ns={k: distribution(v) for k, v in gaps.items()},
        cut_to_hit_reserve_ns={k: distribution(v) for k, v in until_reserve.items()},
    )


def run(a, rec):
    P.file(HERE / "protocol.md", METHOD)
    P.file(
        HERE.parent / "tf32/score.py",
        "7d373bf50126c2c6a058c92705d4d926b42857b96240baa26f11ddfc4862c3e5",
    )
    original = json.loads(P.file(HERE.parent / "tf32/receipt.json", CAL))
    control = {k: original[k] for k in ("method_sha256", "program_sha256")}
    TF["run"](a, control)
    need(control == original, "reproduce calibrated projection")
    captures, _, _ = P.capture(a.part23)
    params = TF["parameters"](a.c7, a.bundle, original["weights_sha256"])
    P.project = TF["surrogate"](params)
    name = "tesy-c292-pack-numeric-physical-20261125-r02/overlay_on/raw/phase.pfj1"
    mf = json.loads(
        P.file(
            a.part95 / "manifest.json",
            "64adf1757a04cab2e30528d2a349c61069034547fe9063722f04071ea48e939d",
        )
    )
    need(mf["files"][name]["sha256"] == JOURNAL, "archive journal membership")
    events, head = AUDIT["read_journal"](a.part95 / name)
    need(head["journal_sha256"] == JOURNAL and head["records"] == 72850, "journal identity")
    rec.update(score(events, captures, params))
    counts = rec["counts"]
    rec["prefill_tier_improved_on_common_history"] = {
        tier: counts[f"prefill/{tier}/projection_paired/four"]["jobs_hit"]
        > counts[f"prefill/{tier}/previous_target/four"]["jobs_hit"]
        for tier in ("CPU", "CUDA")
    }
    rec["status"] = (
        "GO_OBSERVE_AVAILABILITY"
        if all(rec["prefill_tier_improved_on_common_history"].values())
        else "INCONCLUSIVE_ADDITIONAL_VALUE"
    )
    rec.update(journal=head, calibration_sha256=CAL, validated_jobs=4501, physical_prefetches=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("part23", "part95", "c7", "bundle", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    receipt = {
        "status": "FAIL_PRESERVED",
        "method_sha256": METHOD,
        "program_sha256": P.sha(Path(__file__).read_bytes()),
    }
    try:
        run(args, receipt)
    except Exception as e:
        receipt.update(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    with (args.new_output_dir / "receipt.json").open("x") as output:
        json.dump(receipt, output, sort_keys=True, indent=2)
        output.write("\n")
    print(receipt["status"], receipt.get("reason", ""))
    raise SystemExit(int(receipt["status"] == "FAIL_PRESERVED"))
