"""Page coverage conditioned on all T2 target rankings in two sealed natural sessions."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NATURAL = HERE.parents[1] / "igpu_resident_rank/request_budget/device/pack_native/natural_trace"
PRED = run_path(str(NATURAL / "prefill_retention/evaluate.py"))
IK = run_path(str(HERE.parent / "verify.py"))
CHAIN = PRED["CHAIN"]
NATIVE = CHAIN["NATURAL"]
need, sha = IK["need"], IK["sha"]
P97 = PRED["P97"]
P106 = "90750b0ccf87d7f5ceb6d89b6b320e1bf9cf07c0082c1961a31f14b67326aee9"
PAGE, CHUNK, STRIDE = 4096, 2 * 1024**2, IK["STRIDE"]
TIERS = ("CPU", "CUDA0", "all")
SCENARIOS = ("selective", "eligible_full")


def union(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(merged[-1][1], end)
        else:
            merged.append((start, end))
    return merged


def length(spans):
    return sum(end - start for start, end in spans)


@dataclass
class Footprint:
    spans: list
    chunks: int
    chunk_page_bytes: int
    payload_bytes: int
    site_page_bytes: int

    def report(self):
        return {
            "possible_chunks": self.chunks,
            "chunk_page_bytes_with_multiplicity": self.chunk_page_bytes,
            "payload_bytes": self.payload_bytes,
            "site_page_bytes_with_multiplicity": self.site_page_bytes,
            "distinct_page_bytes": length(self.spans),
        }


def footprint(bases, ids):
    need(set(ids) <= set(range(128)), "invalid expert")
    spans = []
    chunks = page_sum = 0
    for _, items in groupby(enumerate(sorted(set(ids))), lambda kv: kv[1] - kv[0]):
        experts = [k for _, k in items]
        for base in bases:
            start = base + experts[0] * STRIDE
            stop = base + (experts[-1] + 1) * STRIDE
            spans.append((start // PAGE * PAGE, -(-stop // PAGE) * PAGE))
            for pos in range(start, stop, CHUNK):
                page_sum += (-(-min(pos + CHUNK, stop) // PAGE) - pos // PAGE) * PAGE
                chunks += 1
    merged = union(spans)
    return Footprint(merged, chunks, page_sum, len(set(ids)) * len(bases) * STRIDE, length(merged))


def aggregate(items):
    return Footprint(
        union(span for item in items for span in item.spans),
        sum(x.chunks for x in items),
        sum(x.chunk_page_bytes for x in items),
        sum(x.payload_bytes for x in items),
        sum(x.site_page_bytes for x in items),
    )


def reopen(p97, p106):
    family, arm, receipt, audit = CHAIN["chain"](p97, P97)
    need(audit["status"] == "PASS_PACK_NATURAL_TRACE", "P97 incomplete")
    checked = NATIVE["audit_arm"](p97 / "ON", receipt, receipt["pack_events"]["before_second_ns"])
    need(json.loads(json.dumps(checked)) == audit, "P97 audit changed")
    rows, header = NATIVE["PFJ"]["read_journal"](p97 / "ON/raw/events.pfj")
    need(header == audit["header"], "P97 PFJ header")
    log = p97 / "ON/raw" / receipt["native_ids"]["raw_stderr_file"]
    need(sha(log) == receipt["native_ids"]["stderr_sha256"], "P97 placement source")
    tiers, _ = PRED["T"]["mapping"](log.read_bytes(), rows)
    geometry = [c["geometry"] for c in NATIVE["host_trace"](rows)["calls"]]
    ranks = PRED["L"]["ranks"](rows, 0)
    bindings = PRED["bindings"](rows)
    del rows
    _, rows, tiers106, proof = PRED["read_new"](p106, P106)
    need(tiers == tiers106 and PRED["bindings"](rows) == bindings, "tier and entry correspondence")
    need(PRED["L"]["ranks"](rows, 0) == ranks and len(ranks) == 7012, "ordered E27 correspondence")
    current = NATIVE["host_trace"](rows)
    need(
        current["route"] == audit["route"]
        and [c["geometry"] for c in current["calls"]] == geometry,
        "native route, pruning or geometry",
    )
    outer = CHAIN["sealed"](p106 / "family.json", P106)
    need(
        arm["grade"]["trajectories"] == outer["arms"]["ON"]["arm"]["grade"]["trajectories"],
        "target trajectory",
    )
    need(len(geometry[2:]) == 46 and current["route"]["rows"] == 7012, "decode calls")
    return (
        ranks,
        geometry,
        tiers,
        {
            "p97_family": P97,
            "p97_pfj": header["journal_sha256"],
            "p106_family": P106,
            "p106_pfj": proof["journal_sha256"],
            "ordered_route": current["route"]["sha256"],
            "inventory": IK["INVENTORY"],
            "p97_observer": family["identity"]["journal_auditor_sha256"],
        },
    )


def sizes_by_tile(ranks, geometry, tiers, bases):
    tiles, sites = [], []
    for call, call_tiles in enumerate(geometry, 1):
        for tile, (width, pos0, pos1) in enumerate(call_tiles, 1):
            parts = {mode: defaultdict(list) for mode in SCENARIOS}
            counts = defaultdict(int)
            for layer in range(36):
                rows = width if layer < 35 else int(call > 1 and tile == len(call_tiles))
                site = call, tile, layer
                experts = set()
                for row in range(rows):
                    quartet = ranks[(*site, row)]
                    need(len(quartet) == len(set(quartet)) == 4, "logical top-4")
                    experts.update(quartet)
                selected = footprint(bases[layer], experts)
                full = footprint(bases[layer], range(128)) if rows >= 32 else selected
                tier = tiers[layer]
                counts["quartets"] += rows
                counts["unique_site_experts"] += len(experts)
                counts["eligible_layers"] += int(rows >= 32)
                for mode, value in zip(SCENARIOS, (selected, full), strict=True):
                    parts[mode][tier].append(value)
                sites.append(
                    (
                        call,
                        tile,
                        layer,
                        tier,
                        rows,
                        4 * rows,
                        len(experts),
                        int(rows >= 32),
                        selected.chunks,
                        selected.chunk_page_bytes,
                        length(selected.spans),
                        full.chunks,
                        full.chunk_page_bytes,
                        length(full.spans),
                    )
                )
            footprints = {}
            for mode, by_tier in parts.items():
                footprints[mode] = {tier: aggregate(by_tier[tier]) for tier in TIERS[:2]}
                footprints[mode]["all"] = aggregate([*by_tier["CPU"], *by_tier["CUDA0"]])
            tiles.append(
                (
                    {
                        "call": call,
                        "tile": tile,
                        "tokens": width,
                        "positions": [pos0, pos1],
                        **counts,
                    },
                    footprints,
                )
            )
    need(sum(t["quartets"] for t, _ in tiles) == len(ranks), "foreign or missing ranked rows")
    return tiles, sites


def phases(tiles):
    result = {}
    for mode in SCENARIOS:
        result[mode] = {}
        for tier in TIERS:
            groups = {}
            for group, inc in (
                ("prefill", lambda c: c <= 2),
                ("decode", lambda c: c >= 3),
                ("T2", lambda c: True),
            ):
                values = [data[mode][tier] for t, data in tiles if inc(t["call"])]
                total = aggregate(values)
                groups[group] = {
                    **total.report(),
                    "tile_page_bytes_with_multiplicity": sum(length(v.spans) for v in values),
                    "max_tile_page_bytes": max(length(v.spans) for v in values),
                }
            groups["prefill_decode_shared_page_bytes"] = (
                groups["prefill"]["distinct_page_bytes"]
                + groups["decode"]["distinct_page_bytes"]
                - groups["T2"]["distinct_page_bytes"]
            )
            result[mode][tier] = groups
    return result


COLUMNS = (
    "call tile layer tesy_tier quartets rank_occurrences distinct_experts eligible32 "
    "selected_chunks selected_chunk_page_bytes selected_page_union_bytes "
    "full_if_eligible_chunks full_if_eligible_chunk_page_bytes full_if_eligible_page_union_bytes"
).split()


def run(a):
    raw = a.inventory.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == IK["INVENTORY"], "C283 metadata")
    ranks, geometry, tiers, sources = reopen(a.p97, a.p106)
    tiles, sites = sizes_by_tile(ranks, geometry, tiers, IK["layer_geometry"](raw))
    need(len(tiles) == 52 and len(sites) == 52 * 36, "tile census")
    totals = phases(tiles)
    path = a.new_output_dir / "sites.tsv"
    with path.open("x") as h:
        w = csv.writer(h, delimiter="\t", lineterminator="\n")
        w.writerow(COLUMNS)
        w.writerows(sites)
    tile_path = a.new_output_dir / "tiles.json"
    data = [
        {**identity, **{m: {t: fp.report() for t, fp in by.items()} for m, by in modes.items()}}
        for identity, modes in tiles
    ]
    with tile_path.open("x") as h:
        json.dump(data, h, separators=(",", ":"), sort_keys=True)
        h.write("\n")
    return {
        "status": "TRACE_DERIVED_NATURAL_GGUF_PAGE_EXTREMES",
        "protocol_sha256": sha(HERE / "protocol.md"),
        "method_sha256": sha(Path(__file__)),
        "sources": sources,
        "tiles_sha256": sha(tile_path),
        "sites_sha256": sha(path),
        "tiles": len(tiles),
        "sites_including_pruned": len(sites),
        "quartets": len(ranks),
        "rank_occurrences": 4 * len(ranks),
        "eligible32_sites": sum(r[7] for r in sites),
        "first_decode": data[6],
        "totals": totals,
        "hardware_io_bytes": None,
        "ik_split_topology_observed": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("p97", "p106", "inventory", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        result = run(a)
    except Exception as error:
        result = {"status": "FAIL_PRESERVED", "error": type(error).__name__, "detail": str(error)}
    with (a.new_output_dir / "receipt.json").open("x") as h:
        json.dump(result, h, sort_keys=True, indent=2)
        h.write("\n")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
