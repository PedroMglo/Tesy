"""Price two adjacent causal tiles against a single-port expert service and host cuts."""

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
GAPS = HERE.parent / "tile_boundary_floor/gaps"
old = run_path(str(GAPS / "screen.py"))
entry, fd, check = old["entry"], old["fd"], old["check"]
METHOD = "6086a90e1c62f6eee2ffe86f76772ad7013a235753120b2394bd5fd2a56cd84e"
GAP_SOURCE = "f1343fc84f4a8b5b35a19c9b5470fd4ca3f6bc74e6776c164449a1f6a4641652"
GAP_RECEIPT = "4a9f2f7c7985120323d5075521e7d89b67c9c08ec182baece3bcf499bd96340b"
TRADEOFF = "94cdca0ef2c2ccc9ee100b265dc87f96c48dcb46e3d2a976cb5c9b37309d99a7"
NS = 1_000_000_000


def pinned(path, digest):
    check(entry.sha(path) == digest, path.name)
    return json.loads(path.read_bytes())


def eligible_gaps(rows, start, historical):
    spans = old["service_index"](rows)
    loading = fifo = epoch = 0
    prev = None
    tier = defaultdict(Counter)
    for r in rows:
        k = r.kind
        if k == 1 and r.call == start + 2:
            break
        if (k == 5 and r.a == 1) or k == 11:
            loading += 1
        if k == 17:
            loading -= 1
        if (k == 6 and r.b == 1) or k == 12:
            fifo += 1
        if k in (13, 14, 28):
            fifo -= 1
        if k in (11, 12, 13, 14, 15, 16, 17, 18, 28):
            epoch += 1
        check(min(loading, fifo) >= 0, "negative pending count")
        if r.call not in (start, start + 1):
            continue
        if k == 23:
            prev = (r, loading == fifo == 0, epoch)
        elif k == 9 and r.a and prev:
            last, idle, old_epoch = prev
            if (r.call, r.tile, r.layer) != (last.call, last.tile, last.layer + 1):
                continue
            if not idle or old_epoch != epoch or old["crosses"](spans, last.ns, r.ns):
                continue
            stage = "A" if last.layer < 24 else "cut" if last.layer == 24 else "B"
            row = tier[f"call{r.call - start + 1}_tile{r.tile}"]
            row[stage] += r.ns - last.ns
            row["count"] += 1
    check(set(tier) == set(historical["tiles"]), "all tiles")
    cost = 0
    for tile, charges in tier.items():
        value = historical["tiles"][tile]
        elapsed = sum(charges[k] for k in ("A", "cut", "B"))
        check((elapsed, charges["count"]) == (value["drained_ns"], value["drained"]), tile)
        cost += elapsed
    protected = sum(tier["call1_tile1"][k] for k in ("A", "cut", "B"))
    protected += tier["call2_tile1"]["A"] + tier["call2_tile5"]["B"]
    check(0 <= protected <= cost == historical["total"]["drained_ns"], "gap partition")
    return dict(tiles=tier, total_ns=cost, protected_ns=protected, eligible_cap_ns=cost - protected)


def host_bounds(rows, call):
    host = [r for r in rows if r.call == call]
    (enter,) = (r.ns for r in host if r.kind == 1)
    (returned,) = (r.ns for r in host if r.kind == 2)
    elapsed = returned - enter
    tiles = []
    last_observed = []
    for t in range(1, 6):
        tile = [r for r in host if r.tile == t]
        (begin,) = (r.ns for r in tile if r.kind == 3)
        (end,) = (r.ns for r in tile if r.kind == 4)
        first = {
            layer: min(r.ns for r in tile if r.layer == layer and r.kind == 9) for layer in (0, 25)
        }
        # Four early tiles can have no last-layer FFN because no output row was
        # requested. Its preceding observed layer widens both cut envelopes.
        final_layer = max(r.layer for r in tile if 25 <= r.layer <= 35 and r.kind == 23)
        last_observed.append(final_layer)
        last = {
            layer: max(r.ns for r in tile if r.layer == layer and r.kind == 23)
            for layer in (24, final_layer)
        }
        chain = [begin, first[0], last[24], first[25], last[final_layer], end]
        check(enter <= begin and end <= returned and sorted(chain) == chain, "tile host cuts")
        tiles.append([n - enter for n in chain])
    check(
        all(x[-1] <= y[0] for x, y in zip(tiles, tiles[1:], strict=False)), "tile submission order"
    )
    pairs = []
    min_path = tiles[0][2] + (elapsed - tiles[-1][3])
    pair_cap = 0
    for i in range(4):
        a_min = tiles[i + 1][2] - tiles[i + 1][1]
        b_min = tiles[i][4] - tiles[i][3]
        # Bound each side by the widest possible allocation of uncertain transition work.
        a_max = tiles[i + 1][3] - tiles[i][4]
        b_max = tiles[i + 1][1] - tiles[i][2]
        check(0 <= a_min <= a_max and 0 <= b_min <= b_max, "stage interval")
        pairs.append(dict(a_min_ns=a_min, a_max_ns=a_max, b_min_ns=b_min, b_max_ns=b_max))
        min_path += max(a_min, b_min)
        pair_cap += min(a_max, b_max)
    worker_spans = defaultdict(list)
    payload = requested = 0
    for r in rows:
        if r.kind not in (15, 16):
            continue
        left, right = max(r.begin, enter), min(r.ns, returned)
        if left < right:
            worker_spans[r.worker].append((left, right))
        if r.call == call:
            check(enter <= r.begin <= r.ns <= returned, "service crossing return")
            if r.kind == 15:
                requested += r.b
            else:
                payload += r.a
    check(len(worker_spans) <= 4, "worker count")
    service = {}
    for worker, spans in worker_spans.items():
        spans.sort()
        check(
            all(x[1] <= y[0] for x, y in zip(spans, spans[1:], strict=False)),
            "overlapping worker service",
        )
        service[worker] = sum(y - x for x, y in spans)
    min_wall = max(min_path, (sum(service.values()) + 3) // 4)
    cap = min(pair_cap, elapsed - min_wall)
    check(0 <= cap <= elapsed, "bounded wall savings")
    return dict(
        call148_elapsed_ns=elapsed,
        tile_markers_relative_ns=tiles,
        last_observed_layer=last_observed,
        pairs=pairs,
        min_path_ns=min_path,
        worker_read_set_service_ns=service,
        four_worker_wall_floor_ns=(sum(service.values()) + 3) // 4,
        r0_requested_gguf_bytes=requested,
        r0_set_payload_bytes=payload,
        host_pair_cap_ns=pair_cap,
        wall_cap_ns=cap,
    )


def combined(prices, gaps):
    output = {}
    for d, banks in prices.items():
        output[d] = {}
        for name, case in banks.items():
            io = case["prefill_payload_s"]
            envelope = case["envelope_s"]
            remaining = gaps["protected_ns"] / NS
            floor = io + remaining
            cap = gaps["eligible_cap_ns"] / NS
            excess = floor + int(d) / 6 - envelope
            check(abs(excess - case["excess_s_at_6"] + cap) < 1e-8, "unique overlap credit")
            output[d][name] = dict(
                payload_s=io,
                min_prefill_s=floor,
                serial_excess_s_at_6=case["excess_s_at_6"],
                remaining_excess_s_at_6=excess,
                max_overhead_s_at_6=max(0, -excess),
                min_decode_rate=int(d) / (envelope - floor) if envelope > floor else None,
                status="NO_GO_CONDITIONAL" if excess > 0 else "HEADROOM_ONLY",
            )
    return output


def run(args):
    check(
        entry.sha(HERE / "protocol.md") == METHOD and entry.sha(GAPS / "screen.py") == GAP_SOURCE,
        "frozen procedure",
    )
    pinned(GAPS.parent / "cuts-receipt.json", old["CUTS"])
    gaps_ref = pinned(GAPS / "receipt.json", GAP_RECEIPT)["arms"]["part-40"]
    trade = pinned(GAPS / "tradeoff-receipt.json", TRADEOFF)["cases"]
    sources = old["source_proof"](args.backend)
    ctx = (
        subprocess.check_output(
            ["git", "-C", args.backend, "rev-parse", old["PIN"] + ":src/llama-context.cpp"],
            timeout=10,
        )
        .decode()
        .strip()
    )
    check(ctx == "8fa5850bc96afba2a1d01d11d1344bd94fcc531e", "scheduler source")
    part, manifest, name, original, journal, start = entry.ARMS[1]
    files = pinned(args.part / "manifest.json", manifest)["files"]
    root = args.part / name
    rec = pinned(root / "receipt.json", original)
    check(part == "part-40" and rec["status"] == "FAIL_PRESERVED" and start == 74, "source capture")
    rows, header = fd.read_journal(root / "raw/events.pfj")
    check(
        header["journal_sha256"] == journal == files[name + "/raw/events.pfj"]["sha256"], "journal"
    )
    _, fifo, busy, _, _ = entry.before_decode(rows, header, start)
    check(not fifo and not busy, "decode handoff")
    gaps = eligible_gaps(rows, start, gaps_ref)
    host = host_bounds(rows, start + 1)
    leg = rec["rows"][1]
    check((leg["predicted_n"], leg["prompt_n"], leg["cache_n"]) == (47, 153, 2044), "client counts")
    raw_pair = {
        d: {
            "r0_prefill_s": leg["prefill_s"],
            "first_final_floor_s_at_decode_6": leg["first_final_s"]
            - leg["decode_s"]
            + int(d) / 6
            - host["wall_cap_ns"] / NS,
        }
        for d in trade
    }
    return dict(
        status="TRACE_DERIVED_CONDITIONAL_PIPELINE_BOUND",
        protocol_sha256=METHOD,
        source_sha256=entry.sha(Path(__file__)),
        backend_pin=old["PIN"],
        context_blob=ctx,
        source_digests=sources,
        archive_manifest_sha256=manifest,
        original_status=rec["status"],
        journal_sha256=journal,
        original_receipt_sha256=original,
        host=host,
        raw_with_decode_at_6=raw_pair,
        gaps=gaps,
        pack_with_freed_tile_cuts=combined(trade, gaps),
        timing="INCONCLUSIVE",
        model_forwards=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("part", "backend", "new-output-dir"):
        parser.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    status = 0
    try:
        result = run(args)
    except Exception as e:
        result = dict(
            status="NOT_RUN_RAW_REQUIRED" if isinstance(e, FileNotFoundError) else "FAIL_PRESERVED",
            reason=f"{type(e).__name__}: {e}",
        )
        status = 1
    tmp = args.new_output_dir / "receipt.tmp"
    with tmp.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    tmp.rename(args.new_output_dir / "receipt.json")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
