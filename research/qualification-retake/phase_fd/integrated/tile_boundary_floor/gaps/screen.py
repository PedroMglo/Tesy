"""Price only drained inter-layer intervals inside the two nominal prefill calls."""

import argparse
import hashlib
import json
import os
import subprocess
from bisect import bisect_left
from collections import Counter, defaultdict, deque
from itertools import accumulate
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
rank = run_path(UNIT / "rank_overlap/screen.py")
entry, fd, check = rank["entry"], rank["fd"], rank["check"]
PROTOCOL = "c3dce68b87a07e0693946f15350af0f3504ac0d4402e5140436903d3399ca6d3"
CUTS = "de7e2eb8b29332ea70cb5013c55e2cd8b23077c537c36a52f119089716ce9801"
LIMITS = "47476b0d8f0435c5e4c04f56a73edbb85f81e22ef9f9ba80a92c3b19b67d5b74"
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
BLOBS = {
    "src/models/openai-moe.cpp": "6d74f9c7e6ef8152f48ed26f608aa41105fbe6e9",
    "src/llama-graph.cpp": "c92f8693ad7b0e0e5756772624b2b83cac9d4ab9",
    "src/llama-moe-stream.cpp": "27c7ca0a170bf99d29a5e91d2edd9a75c18d7059",
}
RATE = 4_500_000_000
PAYLOAD = 13_219_200


def source_proof(repo):
    result = {}
    for name, blob in BLOBS.items():
        data = subprocess.check_output(["git", "-C", repo, "show", f"{PIN}:{name}"], timeout=10)
        check(hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == blob, name)
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def service_index(rows):
    pairs = sorted((r.begin, r.ns) for r in rows if r.kind in (15, 16))
    check(all(0 < a <= b for a, b in pairs), "service span")
    return [a for a, _ in pairs], list(accumulate((b for _, b in pairs), max))


def crosses(index, left, right):
    starts, ends = index
    j = bisect_left(starts, right)
    return j > 0 and ends[j - 1] > left and left < right


def census(rows, start):
    spans = service_index(rows)
    loading, claimed, fifo = set(), set(), deque()
    epochs = 0
    prev = None
    by_tile = defaultdict(Counter)
    outgoing = Counter()
    active = None
    for r in rows:
        k = r.kind
        key = fd.identity(r)
        if k == 5 and r.a == 1:
            loading.add(key)
            if r.b:
                claimed.add(key)
        elif k == 6 and r.b == 1:
            fifo.append(key)
        elif k == 11:
            check(key not in loading, "duplicate reservation")
            loading.add(key)
        elif k == 12:
            fifo.append(key)
        elif k in (13, 14, 28):
            check(fifo and fifo.popleft() == key, "FIFO handoff")
            if k == 13:
                check(key in loading and key not in claimed, "claim identity")
                claimed.add(key)
        elif k == 17:
            check(key in claimed and key in loading, "published generation")
            claimed.remove(key)
            loading.remove(key)
        if k in (11, 12, 13, 14, 15, 16, 17, 18, 28):
            epochs += 1
        if k == 1 and r.call == start + 2:
            break
        if r.call not in (start, start + 1):
            continue
        if k == 9:
            check(active is None, "nested callbacks")
            active = r
            if prev is None:
                continue
            last, idle, epoch = prev
            if (r.call, r.tile, r.layer) != (last.call, last.tile, last.layer + 1):
                continue
            dest = by_tile[(r.call - start + 1, r.tile)]
            dest["neighbor_transitions"] += 1
            if r.a == 0:
                dest["no_next_routes"] += 1
                continue
            check(r.wave in (0, -1) and r.ns >= last.ns, "first callback/clock")
            if not idle or loading or claimed or fifo or epoch != epochs:
                dest["inflight_or_new_work"] += 1
            elif crosses(spans, last.ns, r.ns):
                dest["spanning_service"] += 1
            else:
                gap = r.ns - last.ns
                dest["drained"] += 1
                dest["drained_ns"] += gap
                outgoing["CPU" if last.layer < 25 else "CUDA"] += gap
        if k == 23:
            check(
                active is not None
                and (r.call, r.tile, r.layer, r.wave)
                == (active.call, active.tile, active.layer, active.wave),
                "end identity",
            )
            prev = (r, not (loading or claimed or fifo), epochs)
            active = None
    return by_tile, outgoing


def price(volume, allowance, gap):
    # allowance is an upper rounded byte budget @ RATE; its time allowance is favorable.
    spare = allowance - volume
    denom = allowance * 10**9 - gap * RATE
    return {
        "budget_bytes_at_4p5_GBs": allowance,
        "budget_ns_ceil": (allowance * 10**9 + RATE - 1) // RATE,
        "payload_bytes": volume,
        "spare_bytes_before_gaps": spare,
        "max_gap_ns_before_gaps": spare * 10**9 / RATE,
        "max_observed_gap_fraction": spare * 10**9 / (RATE * gap) if gap else None,
        "retaining_all_gaps_minimum_GBs": volume * RATE / denom if denom > 0 else None,
        "retaining_all_gaps_has_transfer_time": denom > 0,
        "all_gaps_fit_at_4p5_GBs": denom >= volume * 10**9,
    }


def run(a):
    check(entry.sha(HERE / "protocol.md") == PROTOCOL, "gap protocol")
    source = source_proof(a.backend)
    cuts = a.cuts_receipt
    check(entry.sha(cuts) == CUTS, "cuts receipt")
    oracle = json.loads(cuts.read_bytes())
    check(
        oracle["status"] == "REPRODUCED_40_SLOT_OFFLINE_FRONTIER"
        and oracle["program_sha256"] == entry.sha(HERE.parent / "cuts.py"),
        "cut method",
    )
    arm = oracle["arms"]["victims"]
    best = [v for v in arm["cuts"] if v["released_after_tile_of_148"] == [1, 2, 3, 4]]
    check(len(best) == 1 and best[0]["total"] == best[0]["cpu"] + best[0]["cuda"] == 793, "cut")
    volume = best[0]["total"] * PAYLOAD
    limits = UNIT / "nominal-r01/limits.json"
    check(entry.sha(limits) == LIMITS, "other conversation budgets")
    limits = json.loads(limits.read_bytes())["scenarios"]
    scenarios = {"47": "C281_M4_predicted_tokens", "46": "optimistic_AR_post_first_evaluations"}
    arms = {}
    for part, msha, name, rsha, jsha, start in entry.ARMS:
        root = a.archive_root / part
        check(entry.sha(root / "manifest.json") == msha, "archive seal")
        files = json.loads((root / "manifest.json").read_bytes())["files"]
        status = rank["pinned_member"](root, files, name + "/receipt.json")
        raw = rank["pinned_member"](root, files, name + "/raw/T2-result.json")
        check(
            files[name + "/receipt.json"]["sha256"] == rsha
            and raw["accepted"]
            and raw["prefix_gate"] == raw["content_gate"] == "PASS"
            and raw["finish_reason"] == "stop",
            "natural client",
        )
        leg = status["rows"][1]
        check(
            (leg["prompt_n"], leg["cache_n"], leg["predicted_n"]) == (153, 2044, 47),
            "client counts",
        )
        if start > 1:
            check(
                status["status"] == "FAIL_PRESERVED"
                and status["failure"] == "ValueError: T2 host route/order/binding"
                and oracle["journal_sha256"] == jsha,
                "local capture identity",
            )
        else:
            check(status["status"] == "PASS_C281_PFJ_ON", "companion capture")
        rows, header = fd.read_journal(root / name / "raw/events.pfj")
        check(
            header["journal_sha256"] == jsha == files[name + "/raw/events.pfj"]["sha256"],
            "PFJ seal",
        )
        _, fifo, active, _, _ = entry.before_decode(rows, header, start)
        check(not fifo and not active, "decode handoff")
        if start > 1:
            seal = rank["pinned_member"](root, files, name + "/before-t2.json")
            cut = seal["records"]
            check(
                rows[cut].kind == 1
                and rows[cut].call == start
                and entry.audit.record_digest(rows[:cut]) == seal["sha256"],
                "own T1 seal",
            )
        tiles, tiers = census(rows, start)
        check(set(tiles) == {(1, 1), *((2, i) for i in range(1, 6))}, "tile coverage")
        total = sum(tiles.values(), Counter())
        check(
            all(
                t["neighbor_transitions"]
                == sum(
                    t[k]
                    for k in (
                        "drained",
                        "no_next_routes",
                        "inflight_or_new_work",
                        "spanning_service",
                    )
                )
                for t in tiles.values()
            )
            and total["drained_ns"] == sum(tiers.values()),
            "interval conservation",
        )
        arms[part] = {
            "status_original": status["status"],
            "archive_manifest_sha256": msha,
            "journal_sha256": jsha,
            "receipt_sha256": rsha,
            "client_sha256": files[name + "/raw/T2-result.json"]["sha256"],
            "tiles": {f"call{call}_tile{tile}": dict(c) for (call, tile), c in tiles.items()},
            "total": dict(total),
            "gap_ns_by_previous_layer_placement": dict(tiers),
            "transfer_count_scope": "own_oracle" if start > 1 else "transferred_sensitivity_only",
            "denominators": {
                k: price(
                    volume,
                    volume + arm["scenarios"][k]["best_payload_margin_bytes"]
                    if start > 1
                    else limits[n]["budget_bytes"],
                    total["drained_ns"],
                )
                for k, n in scenarios.items()
            },
        }
    return {
        "status": "REPRODUCED_DRAINED_INTERLAYER_INTERVALS",
        "arms": arms,
        "protocol_sha256": PROTOCOL,
        "cuts_receipt_sha256": CUTS,
        "limits_sha256": LIMITS,
        "program_sha256": entry.sha(Path(__file__)),
        "backend_commit": PIN,
        "sources": source,
        "rank_screen_sha256": entry.sha(UNIT / "rank_overlap/screen.py"),
        "loads": 793,
        "payload_each_B": PAYLOAD,
        "nominal_bytes_per_s": RATE,
        "model_forwards": 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive-root", "cuts-receipt", "backend", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = run(a)
    except Exception as e:
        result = {"status": "FAIL_PRESERVED", "reason": f"{type(e).__name__}: {e}"}
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
