"""Recheck both natural clients and price the physical R0 phases on their own clocks."""

import argparse
import json
import math
from collections import Counter, defaultdict
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
INT = HERE.parents[2]
gaps = run_path(str(INT / "tile_boundary_floor/gaps/screen.py"))
entry, fd, need = (gaps[k] for k in ("entry", "fd", "check"))
conv = run_path(str(INT / "conversation/profile.py"))
side = run_path(str(HERE.parent / "review.py"))
sha, pinned = conv["sha"], conv["pinned"]
PRIOR = "5820c6549cbdea26426f30bf037addce3a0332d121da377cb9ccca4b19ab25d8"
METHOD = "4de3f696802a9fbabb2d5b3b7d90a7e86c72bb572c9ca8d2613c948c972c3c15"
RATE = 4_500_000_000
METRICS = ("first_final_s", "valid_wall_s", "prefill_s", "decode_s")


def energy(samples, monitor_s):
    """Integrate only adjacent, observed power samples of the same GPU and PID."""
    t = [s["elapsed_s"] for s in samples]
    need(len(t) >= 2 and 0 <= t[0] < t[-1] <= monitor_s + 0.01, "monitor clock")
    need(len({s["gpu"]["uuid"] for s in samples}) == 1, "GPU identity")
    need(len({s["pid"] for s in samples}) == 1, "server PID")
    joules = covered = 0.0
    for a, b in pairwise(samples):
        dt = b["elapsed_s"] - a["elapsed_s"]
        need(dt > 0, "non-increasing monitor clock")
        p, q = a["gpu"].get("power_w"), b["gpu"].get("power_w")
        if all(type(v) in (float, int) and math.isfinite(v) and v >= 0 for v in (p, q)):
            joules += (p + q) * 0.5 * dt
            covered += dt
    return dict(
        estimated_gpu_j=joules if covered else None,
        first_sample_s=t[0],
        last_sample_s=t[-1],
        covered_s=covered,
        monitor_s=monitor_s,
        largest_gap_s=max(b - a for a, b in pairwise(t)),
        missing_power_samples=sum(s["gpu"].get("power_w") is None for s in samples),
        samples=len(t),
        host_energy_j=None,
    )


def phase_budget(row):
    def ns(field, rounding):
        return int((Decimal(str(row[field])) * 10**9).to_integral_value(rounding=rounding))

    span = 10**10 + ns("prefill_s", ROUND_CEILING) + ns("decode_s", ROUND_CEILING)
    span -= ns("first_final_s", ROUND_FLOOR)
    return {n: span - n * 10**9 // 6 for n in (47, 46)}


def traffic(rows, start):
    groups = defaultdict(Counter)
    for r in rows:
        if r.call < start or r.kind not in (11, 15, 16, 17):
            continue
        phase = "prefill5" if r.call == start else "prefill148" if r.call == start + 1 else "decode"
        stats = groups[phase, "CPU" if r.layer < 25 else "CUDA"]
        stats[fd.NAMES[r.kind]] += 1
        if r.kind == 15:
            need(r.error == 0 and 0 < r.c <= r.b, "short or unsuccessful descriptor read")
            stats.update(requested_bytes=r.b, returned_bytes=r.c)
        if r.kind == 16:
            stats["set_bytes"] += r.a
    need(len(groups) == 6, "per-phase per-tier populations")
    for g in groups.values():
        need(
            g["RESERVE"] == g["PUBLISH"] and 3 * g["PUBLISH"] == g["READ"] == g["SET"],
            "origin generation/read/set counts",
        )
        need(g["set_bytes"] == g["PUBLISH"] * 13_219_200, "encoded weight payload")
    return {f"{phase}_{tier}": dict(stats) for (phase, tier), stats in groups.items()}


def turns(raw, receipt):
    results = []
    for i, row in enumerate(receipt["rows"], 1):
        c = json.loads((raw / f"T{i}-result.json").read_bytes())
        timing, stream = c["timings"], c["stream_metrics"]
        need(
            c["accepted"]
            and c["prefix_gate"] == c["content_gate"] == "PASS"
            and c["finish_reason"] == "stop"
            and stream["done_observed"],
            "functional/stream gate",
        )
        metrics = dict(
            prefill_s=timing["prompt_ms"] / 1000,
            decode_s=timing["predicted_ms"] / 1000,
            first_final_s=stream["first_final_content_chunk_s"],
            valid_wall_s=row["valid_wall_s"],
            decode_tok_s=timing["predicted_per_second"],
        )
        for key, value in metrics.items():
            need(value > 0 and math.isclose(value, row[key], rel_tol=1e-7), "client " + key)
        need(
            c["request_wall_s"] <= metrics["valid_wall_s"] + 0.001
            and c["request_wall_s"] >= metrics["first_final_s"],
            "client wall scope",
        )
        results.append(
            dict(
                **metrics,
                predicted_n=timing["predicted_n"],
                cache_n=timing["cache_n"],
                prompt_n=timing["prompt_n"],
                first_text_s=stream["first_text_chunk_s"],
                transport_s=c["request_wall_s"],
                start_s=c["request_started_monotonic"],
                end_s=c["request_ended_monotonic"],
            )
        )
    need(len(results) == 2 and results[0]["end_s"] <= results[1]["start_s"], "two serial turns")
    return results


def arm(root, mode, expected, history):
    receipt = pinned(root / "receipt.json", expected)
    need(receipt["status"].startswith("PASS_") and receipt["model_launches"] == 1, "arm status")
    need(receipt["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE", "cleanup")
    raw = root / "raw"
    monitor = pinned(raw / (receipt["unit"] + ".json"), receipt["monitor_sha256"])
    need(monitor["returncode"] == 0 and monitor["stop_reason"] == "INTERRUPTED_BY_OWNER", "stop")
    native = conv["trajectories"](raw, receipt, history)
    prior = pinned(INT / "conversation/evidence/receipt.json", PRIOR)
    need(native == prior["ON"]["trajectories"] == prior["OFF"]["trajectories"], "gold")
    calls = turns(raw, receipt)
    rows, hdr = fd.read_journal(raw / "events.pfj")
    need(hdr["journal_sha256"] == receipt["journal_sha256"], "journal sha")
    seal = pinned(root / "before-t2.json", receipt["before_t2_sha256"])
    sel = pinned(root / "before-t2-candidates.json", seal["candidate_file_sha256"])
    cut = seal["records"]
    need(entry.audit.record_digest(rows[:cut]) == seal["sha256"], "actual pre-POST seal")
    recovered = json.loads(json.dumps(entry.audit.capture_prefix(rows[:cut])))
    need(recovered == sel and rows[cut].kind == 1 and rows[cut].a == 5, "causal selection")
    start = rows[cut].call
    _, fifo, active, _, _ = entry.before_decode(rows, hdr, start)
    need(not active and not fifo, "decode handoff")
    policy = None
    file = raw / "policy.bin"
    if mode == "ON":
        header, layers = side["parse_policy"](file.read_bytes())
        need(header[:6] == (1, 1, start, 5, 2044, 2048) and not any(header[-3:]), "snapshot cut")
        need(len(layers) == 36 and all(len(layer) == 169 for layer in layers), "snapshot coverage")
        need(sha(file) == receipt["policy_sha256"], "snapshot identity")
        policy = dict(bytes=file.stat().st_size, sha256=sha(file), calls_at_entry=header[6])
    else:
        need(not file.exists() and not file.is_symlink(), "unexpected OFF snapshot")
    phases = traffic(rows, start)
    tiles, tiers = gaps["census"](rows, start)
    counts = sum(tiles.values(), Counter())
    need(counts["drained_ns"] == sum(tiers.values()), "gap union")
    samples_file = raw / (receipt["unit"] + ".samples.jsonl")
    samples = [json.loads(line) for line in samples_file.read_bytes().splitlines()]
    need(all(s["pid"] == monitor["process_identity"]["pid"] for s in samples), "PID in telemetry")
    need(all(s["cgroup"]["swap_current"] == s["cgroup"]["swap_max"] == 0 for s in samples), "swap")
    total = sum(phases[f"decode_{tier}"]["returned_bytes"] for tier in ("CPU", "CUDA"))
    return dict(
        receipt_sha256=expected,
        journal_sha256=hdr["journal_sha256"],
        records=hdr["records"],
        trajectories=native,
        turns=calls,
        interturn_s=calls[1]["start_s"] - calls[0]["end_s"],
        decoded_fd_bytes_per_output_token=total / 47,
        decoded_fd_bytes_per_evaluation=total / 46,
        seal_sha256=seal["sha256"],
        selected_bank_sha256=seal["candidate_file_sha256"],
        policy=policy,
        phase_tier=phases,
        deadlines_prefill_ns=phase_budget(calls[1]),
        prefill_gaps=dict(counts),
        prefill_gaps_ns_by_previous_tier=dict(tiers),
        monitor_sha256=receipt["monitor_sha256"],
        sample_sha256=sha(samples_file),
        physical_maxima=monitor["maxima"],
        energy=energy(samples, monitor["elapsed_s"]),
        ready_s=receipt["ready_s"],
        envelope_including_cleanup_s=receipt["envelope_s"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "history", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    for key in ("off-sha256", "on-sha256"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        need(sha(HERE / "accounting.md") == METHOD, "accounting contract")
        arms = {
            m: arm(a.family / m, m, h, a.history)
            for m, h in (("OFF", a.off_sha256), ("ON", a.on_sha256))
        }
        ratios = [
            {m: b[m] / a_[m] for m in METRICS}
            for a_, b in zip(arms["OFF"]["turns"], arms["ON"]["turns"], strict=True)
        ]
        result = dict(
            status="REPRODUCED_SNAPSHOT_CLIENT_PAIR",
            arms=arms,
            ratios_on_off=ratios,
            t2_in_descriptive_band=all(0.85 <= r <= 1.15 for r in ratios[1].values()),
            method_sha256=METHOD,
            program_sha256=sha(Path(__file__)),
        )
    except (ValueError, OSError, KeyError, IndexError, RuntimeError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    tmp = out / "report.tmp"
    with tmp.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.rename(out / "receipt.json")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
