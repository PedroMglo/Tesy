"""Conditional upper bounds on overlapping same-wave FFN work with outstanding weight delivery."""

import argparse
import importlib.util
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "sealed_decode_entry", HERE.parent / "t1_manager_bank/decode_entry/compare.py"
)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
fd, check = entry.fd, entry.check
PROTOCOL = "49b62dd7ba2ed8a807a6d749255e2d53de499e5a2f808556d9b6538c5f1476a7"
METHOD = "d5321a870115d479ea5d53016a1796bda52dff0d343984d9aa05e92676a384d4"


@dataclass
class Wave:
    call: int
    tile: int
    layer: int
    ordinal: int
    nrows: int
    begin: int
    end: int = 0
    demand: list = field(default_factory=list)


def collect(rows, start_call):
    ready = {}
    waves = []
    current = None
    for row in rows:
        key = fd.identity(row)
        if row.kind == 5 and row.a == 2:
            check(key not in ready, "duplicate initial READY")
            ready[key] = 0
        if row.kind == 17:
            check(key not in ready, "multiple READY transitions for a generation")
            ready[key] = row.ns
        if row.call < start_call:
            continue
        if row.kind == 9:
            check(current is None, "nested remap")
            current = Wave(row.call - start_call + 1, row.tile, row.layer, row.wave, row.a, row.ns)
            waves.append(current)
        elif row.kind == 10:
            check(current is not None, "demand outside remap")
            current.demand.append(key)
        elif row.kind == 23:
            check(current is not None and current.begin <= row.ns, "remap end")
            current.end = row.ns
            current = None
    check(current is None and waves, "unfinished wave")
    return waves, ready


def opportunity(w, after, ready):
    check(len(set(w.demand)) == len(w.demand), "duplicate demand")
    bounds = [max(w.begin, ready[key]) for key in w.demand]
    check(all(t <= w.end for t in bounds), "demand finished after remap")
    hits = sum(t == w.begin for t in bounds)
    lead = max(bounds) - min(bounds) if bounds else 0
    gap = None
    if after:
        check(w.end <= after.begin, "nonserial callbacks")
        if (w.call, w.tile) == (after.call, after.tile) and (w.layer == after.layer or after.nrows):
            gap = after.begin - w.end
    gain = lead if gap is None else min(lead, gap)
    return {
        "waves": 1,
        "demanded_generations": len(bounds),
        "ready_at_entry": hits,
        "parking_only_waves": int(not bounds),
        "all_ready_waves": int(bool(bounds) and hits == len(bounds)),
        "mixed_at_entry_waves": int(0 < hits < len(bounds)),
        "all_pending_waves": int(bool(bounds) and hits == 0),
        "eligible_resident_waves": int(bool(hits and lead)),
        "eligible_progressive_waves": int(lead > 0),
        "no_proven_compute_fence_waves": int(gap is None),
        "resident_upper_ns": gain if hits else 0,
        "progressive_upper_ns": gain,
        "lead_ns": lead,
        "reduction_from_next_callback_upper_ns": lead - gain,
    }


def summarize(waves, ready, start, first, decode):
    totals = defaultdict(Counter)
    for i, w in enumerate(waves):
        obs = opportunity(w, waves[i + 1] if i + 1 < len(waves) else None, ready)
        phase = "prefill_5" if w.call == 1 else "prefill_148" if w.call == 2 else "decode"
        totals[phase].update(obs)
        totals[phase + ("_CPU" if w.layer < 25 else "_CUDA")].update(obs)
        if w.begin <= first + 1_000_000:
            totals["first_final"].update(obs)
            totals["first_final" + ("_CPU" if w.layer < 25 else "_CUDA")].update(obs)
    decisions = {}
    for phase, baseline, target in (
        ("first_final", first - start - 1_000_000, 10**10),
        ("decode", decode, math.ceil(47 * 1e9 / 6)),
    ):
        decisions[phase] = {}
        for policy in ("resident", "progressive"):
            bound = totals[phase][policy + "_upper_ns"]
            sites = totals[phase]["eligible_" + policy + "_waves"]
            margin = target - (baseline - bound)
            decisions[phase][policy] = {
                "upper_gain_ns": bound,
                "conditional_floor_ns": baseline - bound,
                "target_ns": target,
                "margin_ns": margin,
                "eligible_waves": sites,
                "max_total_additional_cost_ns": max(0, margin),
                "max_uniform_additional_cost_ns_per_eligible_wave": max(0, margin) // sites
                if sites
                else None,
                "decision": "NO_GO_UNCHANGED_SERVICE" if margin < 0 else "HEADROOM_ONLY",
            }
    return {"phase": dict(totals), "decisions": decisions}


def pinned_member(root, manifest, name):
    entry_ = manifest[name]
    file = root / name
    check(
        file.stat().st_size == entry_["bytes"] and entry.sha(file) == entry_["sha256"],
        "archived member " + Path(name).name,
    )
    return json.loads(file.read_bytes())


def run(root):
    check(entry.sha(HERE / "protocol.md") == PROTOCOL, "preregistered protocol")
    result = {}
    for part, msha, name, rsha, jsha, first_call in entry.ARMS:
        folder = root / part
        check(entry.sha(folder / "manifest.json") == msha, "archive manifest")
        files = json.loads((folder / "manifest.json").read_bytes())["files"]
        raw = pinned_member(folder, files, name + "/raw/T2-result.json")
        receipt = pinned_member(folder, files, name + "/receipt.json")
        check(files[name + "/receipt.json"]["sha256"] == rsha, "capture receipt")
        check(
            raw["accepted"]
            and raw["prefix_gate"] == raw["content_gate"] == "PASS"
            and raw["finish_reason"] == "stop",
            "accepted client",
        )
        leg = receipt["rows"][1]
        check(
            leg["prompt_n"] == 153 and leg["cache_n"] == 2044 and leg["predicted_n"] == 47,
            "work denominators",
        )
        check(
            (
                receipt["status"] == "PASS_C281_PFJ_ON"
                if first_call == 1
                else receipt["status"] == "FAIL_PRESERVED"
                and receipt["failure"] == "ValueError: T2 host route/order/binding"
            ),
            "original capture status",
        )
        rows, h = fd.read_journal(folder / name / "raw/events.pfj")
        check(jsha == h["journal_sha256"] == files[name + "/raw/events.pfj"]["sha256"], "journal")
        # The shared auditor rechecks all calls, ranks, reserves, claims, SET and publication.
        _, fifo, workers, _, meta = entry.before_decode(rows, h, first_call)
        check(not fifo and not workers, "initial decode handoff")
        if first_call > 1:
            seal = pinned_member(folder, files, name + "/before-t2.json")
            cut = seal["records"]
            check(
                rows[cut].kind == 1
                and rows[cut].call == first_call
                and entry.audit.record_digest(rows[:cut]) == seal["sha256"],
                "sealed T1/T2 cut",
            )
        start = math.floor(raw["request_started_monotonic"] * 1e9)
        first = start + math.ceil(raw["stream_metrics"]["first_final_content_chunk_s"] * 1e9)
        decode = math.floor(leg["decode_s"] * 1e9)
        check(abs((first - start) / 1e9 - leg["first_final_s"]) < 1e-6, "client and endpoint clock")
        waves, ready = collect(rows, first_call)
        check(
            start <= waves[0].begin and first <= math.ceil(raw["request_ended_monotonic"] * 1e9),
            "T2 window",
        )
        prices = summarize(waves, ready, start, first, decode)
        check(
            sum(prices["phase"][p]["waves"] for p in ("prefill_5", "prefill_148", "decode"))
            == len(waves),
            "phase count",
        )
        result[part] = {
            "original_capture_status": receipt["status"],
            "manifest_sha256": msha,
            "receipt_sha256": rsha,
            "journal_sha256": jsha,
            "client_sha256": files[name + "/raw/T2-result.json"]["sha256"],
            "capture_first_call_number": first_call,
            "first_final_ns": first - start,
            "decode_ns": decode,
            "prefill_ns": math.floor(leg["prefill_s"] * 1e9),
            "decode_handoff_record": meta["cut_record_index_zero_based"],
            **prices,
        }
    return {
        "status": "PASS_OFFLINE_RANK_OVERLAP_BOUND",
        "protocol_sha256": PROTOCOL,
        "screen_sha256": entry.sha(Path(__file__)),
        "arms": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    try:
        r = run(args.archive_root)
    except Exception as exc:
        r = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
