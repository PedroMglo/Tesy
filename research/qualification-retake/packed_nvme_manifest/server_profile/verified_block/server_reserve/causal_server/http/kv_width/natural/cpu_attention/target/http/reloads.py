"""Count only C291 packed reads with an earlier consumer in the same 148-token call."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
IO = run_path(str(HERE / "prefill_io.py"))
H, G, R, need, sha, save = (IO[k] for k in ("H", "G", "R", "need", "sha", "save"))
TRACE = H["Q"] / "igpu_resident_rank/request_budget/device/pack_native/natural_trace"
C = run_path(str(TRACE / "prefill_retention/request_cost/score.py"))
Q = C["Q"]
SERVICE = run_path(str(TRACE / "jobs.py"))
WINDOW, PAYLOAD = SERVICE["WINDOW"], 3 * SERVICE["SLAB"]
ARCH = run_path(str(H["Q"] / "private_archive/verify.py"))
METHOD = "f19027b1763ac8af6065e448321e3a18cd943ce208fdcb36d0336f1d5fd35274"
IO_PIN = "b29198b294b35206293895a01f734428fa49ddd32a2ec5e235e0d0b4ba9b4183"


def earlier(demands, generation, site):
    first = demands[generation]
    need(
        first[:3] == site[:3] and first[3] in (site[3], site[3] + 1),
        "reservation and first consumer",
    )
    return first


def repeat(first_tile, use, expert):
    call, tile, layer, _ = use
    return call == 2 and first_tile[call, layer, expert] < tile


def faults():
    seen = {(1, 0, 17): 1, (2, 0, 17): 1, (2, 1, 17): 3}
    previous = (2, 1, 0, 0)
    preloaded = (2, 3, 0, 1)
    actual = earlier({"hot": (2, 3, 0, 2)}, "hot", preloaded)
    checks = dict(
        initial_hit=repeat(seen, actual, 17),
        preload=actual[3] == 2,
        other_layer=not repeat(seen, (2, 3, 1, 0), 17),
        call_boundary=not repeat(seen, previous, 17) and not repeat(seen, (1, 1, 0, 0), 17),
    )
    need(all(checks.values()), "reload controls")
    return checks


def account(rows, tiers):
    _, reserves = C["timeline"](rows)
    consumers = {}
    first_tile = {}
    reads = defaultdict(list)
    tiles = {}
    for r in rows:
        site = C["origin"](r)
        key = C["key"](r)
        if r.kind == 10:
            consumers.setdefault(key, site)
            call, tile, layer, _ = site
            v = (call, layer, r.expert)
            first_tile[v] = min(tile, first_tile.get(v, tile))
            tiles.setdefault((call, tile), set()).add((layer, r.expert))
        elif r.kind == 30:
            reads[key].append(r)
    need(set(reads) == set(reserves) and len(reserves) == 2354, "served generations")
    need(
        sorted(t for c, t in tiles if c == 1) == [1]
        and sorted(t for c, t in tiles if c == 2) == [1, 2, 3, 4, 5],
        "external calls and tile sites",
    )
    counts = defaultdict(Counter)
    seal = []
    for key, site in sorted(reserves.items()):
        use = earlier(consumers, key, site)
        call, tile, layer, _ = use
        _, expert = C["expert"](key)
        read = reads[key]
        need(
            len(read) == 1
            and read[0].b == WINDOW
            and PAYLOAD <= read[0].c <= WINDOW
            and read[0].error == 0
            and read[0].a == (layer * 128 + expert) * SERVICE["STRIDE"],
            "one successful aligned pack read",
        )
        eligible = repeat(first_tile, use, expert) if call in (1, 2) else False
        seal.append([list(key), site, use, eligible, read[0].b, read[0].c])
        if call > 2:
            continue
        group = counts[(call, tile, tiers[layer])]
        group["reservations"] += 1
        if eligible:
            group["reloads"] += 1
            group["aligned_bytes"] += read[0].b
            group["returned_bytes"] += read[0].c
            group["payload_bytes"] += PAYLOAD
    total = Counter()
    for g in counts.values():
        total.update(g)
    need(
        total["reservations"] == 1263 and 0 < total["reloads"] < total["reservations"],
        "prefill coverage",
    )
    return dict(
        tiles=[dict(call=c, tile=t, tier=k, **counts[c, t, k]) for c, t, k in sorted(counts)],
        total=dict(total),
        complete_generations=len(seal),
        classification_sha256=hashlib.sha256(
            json.dumps(seal, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def read_arm(a, label, tiers, data, steps):
    ref = C["SOURCES"][label]
    part = "part-" + label[1:]
    receipt = H["read"](H["Q"] / "private_archive" / (part + ".json"))
    ARCH["verify"](a.archive, receipt)
    root = a.archive / part / ref[0]
    track = root / "ON/raw"
    log = next(track.glob("*.stderr")).read_bytes()
    ids = []
    for i, name in enumerate(("T1", "T2"), 1):
        x = H["read"](track / (name + "-result.json"))
        evidence = H["T"]["grade"](log, i, data, steps, "P")
        need(
            x["accepted"]
            and x["content_gate"] == "PASS"
            and x["official_ids"] == data[name]["prompt"]
            and x["timings"]["cache_n"] == (0, 2044)[i - 1]
            and x["timings"]["prompt_n"] == (2043, 153)[i - 1],
            "natural requests",
        )
        ids.append(evidence["sampled_sha256"])
    if label == "P106":
        _, rows, tiers, _ = Q["read_new"](root, ref[1])
    else:
        _, _, _, snapshot = C["CHAIN"]["chain"](root, ref[1])
        rows, header = Q["T"]["PFJ"]["read_journal"](track / "events.pfj")
        need(header == snapshot["header"], "complete old journal")
    need(
        len(tiers) == 36 and all(tiers[i] == ("CPU" if i < 25 else "CUDA0") for i in range(36)),
        "tier placement",
    )
    return account(rows, tiers), tiers, ids


def study(a):
    head, tree = G["tree"](G["REPO"])
    need(a.commit == head and sha(HERE / "reload-protocol.md") == METHOD, "sealed study")
    iorec = G["read"](a.io / "result.json", IO_PIN)
    filt = G["read"](a.context / "result.json", IO["FILTER"])
    data, steps = R["cases"](a)
    first, tiers, ids = read_arm(a, "P106", None, data, steps)
    second, _, also = read_arm(a, "P97", tiers, data, steps)
    need(first == second and ids == also, "two identical populations and full target IDs")
    cap = first["total"]["aligned_bytes"]
    scenarios = {}
    for label, out in iorec["OFF_nominal_prefill_scenarios"].items():
        short = out["minimum_removed_bytes"]
        s = dict(
            zero_unknown_deficit_bytes=short,
            headroom_bytes=cap - short,
            optimistic_ceiling_covers_deficit=cap >= short,
            max_additional_exposed_cost_s=(cap - short) / IO["RATE"],
        )
        if label.startswith("context_filter"):
            name = label.removeprefix("context_filter_free_new_groups_")
            u = Decimal(
                str(
                    filt["turns"]["T2"]["pricing"][name][
                        "available_new_cost_or_residency_change_to_six_s"
                    ]
                )
            )
            # Round the extra service requirement down in bytes to favor the intervention.
            extra = int(u * IO["RATE"])
            s.update(
                at_six_new_cost_s=float(u),
                at_six_deficit_bytes=short + extra,
                at_six_missing_after_all_reloads_bytes=max(0, short + extra - cap),
            )
        scenarios[label] = s
    return dict(
        status="TRACE_DERIVED_OPTIMISTIC_RELOAD_CEILING",
        commit=head,
        tree=tree,
        protocol_sha256=METHOD,
        io_sha256=IO_PIN,
        context_sha256=IO["FILTER"],
        arms=["P97", "P106"],
        target_id_digests=ids,
        aligned_window_bytes=WINDOW,
        logical_payload_bytes=PAYLOAD,
        fixture=faults(),
        population=first,
        projected=scenarios,
        model_starts=0,
        http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "io", "context", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        res = study(a)
    except Exception as e:
        res = dict(
            status="FAIL_PRESERVED",
            error=f"{type(e).__name__}: {e}",
            commit=a.commit,
            protocol_sha256=METHOD,
        )
    save(a.new_output_dir / "result.json", res)
    print(res["status"], res.get("error", ""))
    raise SystemExit(res["status"] == "FAIL_PRESERVED")
