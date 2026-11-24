#!/usr/bin/env python3
"""Reconcile C135/C136 natural warm-prefill evidence without accessing the model."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
SPECS = (
    (
        "c135-slots40-warm153-trace-20260929T2205Z",
        "c135-c75-slots40-warm153",
        "9ab37fd286df45272a35ff64d107671f4583afa8d6894e1dc6ea5b960d29d8b1",
        "PASS_DIAGNOSTIC_CAPTURE",
    ),
    (
        "c136-slots40-trace-neutral-20260929T2205Z",
        "c136-c75-slots40-neutral",
        "9f8de2cf65fd8434e02b50fb36c8edc5a7e2ceeab1c697e856eeeb873d64e8e9",
        "PASS_TRACE_OFF_NEUTRAL",
    ),
)
ROLE = 4_406_400
WIRE = 1_250_000_000
TRACE_SHA = "91610b12291d5a42a12bba09f5d4ff188d25ee0001ab89e894bdd508005e82fb"
CPP_SHA = "b7ca5f9608f4c20140a51748f88ff64657c0d586f0edc527d4cabd5fd39f2d4c"


def check(value, label):
    if not value:
        raise ValueError(label)


def metadata(root, spec):
    family, arm, pin, status = spec
    canonical = (HERE / "results" / family / "manifest.json").read_bytes()
    check(hashlib.sha256(canonical).hexdigest() == pin, "raw manifest changed")
    files = json.loads(canonical)["files"]

    def raw(suffix):
        name = "raw/" + arm + suffix
        data = (root / family / name).read_bytes()
        row = files[name]
        check(
            len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"],
            "size or digest mismatch",
        )
        return data

    run = json.loads(raw(".json"))
    receipt = json.loads(raw(".receipt.json"))
    ids = json.loads(raw(".tokenization.json"))
    check(
        receipt["status"] == status
        and run["returncode"] == 0
        and not run["stop_reasons"]
        and run["cgroup_end"]["memory_max"] == 18 * 2**30,
        "invalid bounded run",
    )
    first, warm = run["results"]
    check(
        first["id"] == "c112-code"
        and warm["id"] == "c112-repeat"
        and len(ids[warm["id"]]) == 2197
        and warm["timings"]["prompt_n"] == 153
        and warm["timings"]["cache_n"] == 2044
        and warm["timings"]["predicted_n"] == 47,
        "natural request identity",
    )
    samples = [json.loads(line) for line in raw(".samples.jsonl").splitlines()]
    fds = [
        s["model_fds"] for s in samples if warm["started_s"] <= s["elapsed_s"] <= warm["ended_s"]
    ]
    check(
        fds and all(fd == {"open": 1, "direct": 1, "buffered": 0} for fd in fds), "direct model FD"
    )
    metrics = {
        "cap_bytes": 18 * 2**30,
        "gguf_direct_fd_samples": len(fds),
        "warm_prefill_s": warm["timings"]["prompt_ms"] / 1000,
        "warm_decode_s": warm["timings"]["predicted_ms"] / 1000,
        "warm_client_first_final_s": warm["stream_metrics"]["first_final_content_chunk_s"],
    }
    output = [
        (item["message"], item["usage"]["completion_tokens"], item["finish_reason"])
        for item in run["results"]
    ]
    return raw, ids, output, warm, metrics


def count_trace(path, warm):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE / "tools"))
    from c122_trace_validate import HEADER, validate

    validated = validate(path)
    calls = validated["calls"]
    check(
        [(calls[i]["n_tokens"], calls[i]["first_pos"], calls[i]["last_pos"]) for i in (1, 2)]
        == [(5, 2044, 2048), (148, 2049, 2196)],
        "wrong prefill geometry",
    )
    start_ns = warm["monotonic_request_markers_ns"]["request_start"]
    check(
        start_ns <= calls[1]["start_us"] * 1000
        and calls[2]["end_us"] * 1000
        <= start_ns + warm["stream_metrics"]["first_final_content_chunk_s"] * 1e9,
        "prefill crosses first final",
    )
    active, waiting, matched, complete, reads = {}, set(), set(), set(), Counter()
    last = {}
    reloads = Counter()
    tile, previous = -1, 36
    widths = {1: [], 2: []}
    for line in path.open():
        parts = line.rstrip().split("\t")
        if len(parts) != len(HEADER) or parts[0] == "kind":
            continue
        kind = parts[0]
        _, t, layer, e, slot, _, n, wave, state, size, c, gen, _ = map(int, parts[1:])
        if c not in (1, 2):
            continue
        key = c, layer, e, slot, gen
        if kind == "CALL_BEGIN":
            tile, previous = -1, 36
        elif kind == "EVICT":
            active.pop((layer, slot), None)
        elif kind == "DEMAND":
            if layer < previous:
                check(layer == 0 and wave in (-1, 0), "unidentified tile")
                tile += 1
                widths[c].append(n)
            previous = layer
            if state == 2:
                last[layer, e] = (c, tile)
            if state == 0:
                waiting.add((c, layer, e))
            elif (layer, slot) in active:
                reservation = active[layer, slot]
                check(reservation[2] == e, "wrong expert")
                matched.add(reservation)
        elif kind == "ENQUEUE":
            active[layer, slot] = key
            if (c, layer, e) in waiting:
                waiting.remove((c, layer, e))
                matched.add(key)
        elif kind == "LOAD_BEGIN":
            prev = last.get((layer, e))
            if prev and prev[0] == c and prev[1] != tile:
                reloads["CPU" if layer < 25 else "CUDA0"] += 1
            last[layer, e] = (c, tile)
        elif kind in ("READ_BEGIN", "READ_END"):
            check(
                calls[c]["start_us"] <= t <= calls[c]["end_us"] and size == ROLE,
                "read outside call or incompatible size",
            )
            if kind == "READ_END":
                reads[key] += 1
        elif kind == "LOAD_END":
            check(calls[c]["start_us"] <= t <= calls[c]["end_us"], "completion outside call")
            complete.add(key)
    check(widths == {1: [5], 2: [32, 32, 32, 32, 20]}, "tile widths")
    check(
        complete == set(reads) == matched and not waiting and set(reads.values()) == {3},
        "unmatched generation or demand",
    )
    counts = Counter(key[0] for key in complete)
    check(reloads == {"CPU": 102, "CUDA0": 82}, "cross-tile load candidates differ")
    return {
        "calls": [
            {
                "call": c,
                "tokens": calls[c]["n_tokens"],
                "loads": counts[c],
                "bytes": counts[c] * ROLE * 3,
                "wire_floor_s": counts[c] * ROLE * 3 / WIRE,
            }
            for c in (1, 2)
        ],
        "verified_consumed_generations": len(matched),
        "wire_floor_s": len(matched) * 3 * ROLE / WIRE,
        "cross_tile_candidates": dict(reloads),
        "wire_floor_after_removing_all_candidates_s": (len(matched) - sum(reloads.values()))
        * 3
        * ROLE
        / WIRE,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--historical-results", type=Path, required=True)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(exist_ok=False)
    try:
        check(
            hashlib.sha256((a.backend / "src/llama-moe-stream.cpp").read_bytes()).hexdigest()
            == CPP_SHA,
            "source pin",
        )
        usb = json.loads((Path(__file__).parent / "usb-evidence/receipt.json").read_text())
        check(usb["wire"]["wire_bits_s"] == 8 * WIRE, "USB condition changed")
        r1, ids1, out1, warm, on = metadata(a.historical_results, SPECS[0])
        _, ids2, out2, _, off = metadata(a.historical_results, SPECS[1])
        check(ids1 == ids2 and out1 == out2, "paired inputs or outputs changed")
        check(hashlib.sha256(r1(".expert.trace")).hexdigest() == TRACE_SHA, "trace pin")
        path = a.historical_results / SPECS[0][0] / "raw" / (SPECS[0][1] + ".expert.trace")
        other = json.loads(
            next((HERE / "results").glob("c276-*/development-inputs.json")).read_text()
        )
        changed = [
            i
            for i, (x, y) in enumerate(
                zip(ids1["c112-repeat"], other["nominal153"]["ids"], strict=True)
            )
            if x != y
        ]
        proof = count_trace(path, warm)
        result = {
            "evidence": "CONDITIONAL_FORMAL_EXACT_SAME_READS_ON_USB",
            "link_bytes_s": WIRE,
            "source_sha256": CPP_SHA,
            "trace_sha256": TRACE_SHA,
            "on": on,
            "off": off,
            "off_prefill_expert_bytes": "UNIDENTIFIED",
            "input_mismatch_c276_positions": changed,
            "maximum_complete_3role_loads_in_10s": 10 * WIRE // (3 * ROLE),
            "proof": proof,
        }
    except Exception as exc:
        (a.new_output_dir / "FAIL.txt").write_text(type(exc).__name__ + "\n")
        raise
    tmp = a.new_output_dir / ".receipt.pending"
    tmp.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
