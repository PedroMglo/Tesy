"""Price an ideal replacement for CPU expert arithmetic on two authenticated natural turns."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
METHOD = "7e97f778591037025a67947a147954d142cbb8a90b81460e452e5391fb9e439e"
NATURAL = "1fc2ea613bce1d908ca0612a1e745876323b2368f1c560c874ab30f5c4c0424f"
LIMITS = {"first_final": 10_000_000_000, "decode": 47_000_000_000 // 6}
PPM = 1_000_000
PHASES = {
    "first_final": ("prefill", "decode_before_final"),
    "decode": ("decode_before_final", "decode_tail"),
}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def nested_client(path):
    need(sha(path) == NATURAL, "trace-off HTTP seal")
    arms = json.loads(path.read_bytes())["client"]["arms"]
    need(
        [a["role"] for a in arms] == ["ORIGINAL", "OFF", "ON", "ON", "OFF", "ORIGINAL"],
        "HTTP order",
    )
    out = []
    for a in arms:
        t, n = a["turns"][1], a["native_t2"]
        need(
            t["cached"] == 2044
            and t["evaluated"] == 153
            and t["output"] == n["sampled"] == 47
            and n["serial_feeds"] == 46
            and n["first_final_sample"] == 45,
            "causal HTTP boundary",
        )
        inner = n["start_to_sample_1_us"] + n["first_to_feed_44_us"]
        need(0 <= inner / 1e6 <= t["first_final_s"], "native interval exceeds client")
        out.append(
            dict(
                role=a["role"],
                native_to_feed_44_us=inner,
                first_final_s=t["first_final_s"],
                exterior_at_most_s=t["first_final_s"] - inner / 1e6,
                native_saving_required_even_free_exterior_us=max(0, inner - 10_000_000),
            )
        )
    return out


def price(observed, credits, exterior):
    result = {}
    for free in (False, True):
        row = {}
        for metric, limit in LIMITS.items():
            start = observed[metric] - (exterior[metric] if free else 0)
            available = sum(credits[phase] for phase in PHASES[metric])
            need(0 <= available <= start, "discount exceeds native or client time")
            gap = max(0, start - limit)
            ppm = (
                0
                if gap == 0
                else ((gap * PPM + available - 1) // available if available >= gap else None)
            )
            if ppm:
                need(
                    start - (available * ppm // PPM)
                    <= limit
                    < start - available * (ppm - 1) // PPM,
                    "break-even rounding",
                )
            row[metric] = dict(
                observed_ns=observed[metric],
                removable_ns=available,
                floor_ns=start - available,
                missing_even_free_ns=max(0, gap - available),
                min_fraction_ppm=ppm,
            )
        ppm = [r["min_fraction_ppm"] for r in row.values()]
        row["joint_min_fraction_ppm"] = None if None in ppm else max(ppm)
        result["free_exterior" if free else "full_client"] = row
    return result


def analyse(repo, archive):
    family = repo / "research/ready-experts"
    native = run_path(family / "screen.py")
    src = native["SOURCE"]
    dead = run_path(family / "renewal/deadlines.py")
    co = dead["CO"]
    prior = src["pinned"](
        native["NATURAL"] / "prefill_retention/request_cost/receipt.json", native["PRIOR"]
    )
    prefill = src["pinned"](co["LOOKUP"] / "empty-result.json", co["EMPTY_RESULT"])
    traces = {}
    for label in ("P97", "P106"):
        (calls, first, decode), auth = native["read_arm"](archive, label, prior[label])
        name, fsha, _ = src["SOURCES"][label]
        root = archive / ("part-" + label[1:]) / name
        if label == "P106":
            _, rows, _, _ = src["Q"]["read_new"](root, fsha)
        else:
            rows, _ = src["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
        host = src["NATIVE"]["host_trace"](rows)
        waves, releases = src["timeline"](rows)
        reserve, pub, reads, sets = {}, {}, {}, defaultdict(list)
        for e in rows:
            key = src["key"](e)
            if e.kind == 11:
                reserve[key] = e.ns
            elif e.kind == 17:
                pub[key] = e.ns
            elif e.kind == 30:
                reads[key] = e.ns - e.begin
            elif e.kind == 16:
                sets[key].append(e.ns - e.begin)
        need(
            reserve.keys() == pub.keys() == reads.keys() == sets.keys() == releases.keys(),
            "worker ledger",
        )
        tags = dead["consumers"](waves, {k: (ts, pub[k]) for k, ts in reserve.items()})
        need(
            Counter(tags.values()) == {"same_wave": 1918, "later_wave_same_tile_layer": 436},
            "every generation has a consumer in the same tile/layer",
        )
        jobs = defaultdict(list)
        for key, (num, tile, layer, _) in releases.items():
            c = host["calls"][num - 1]
            need(
                c["enter_ns"] <= reserve[key] <= pub[key] <= c["return_ns"] and len(sets[key]) == 3,
                "call-local service duration and three SET",
            )
            jobs[num, tile, layer].append(reads[key] + sum(sets[key]))
        by_call = defaultdict(list)
        for wave in waves:
            by_call[wave.site[0]].append(wave)
        phases = defaultdict(Counter)
        phase_calls = Counter()
        for c, baseline in zip(host["calls"], calls, strict=True):
            num, span = c["number"], baseline.span
            ws = by_call[num]
            phase = native["phase"](num)
            phase_calls[phase] += 1
            d = Counter(entry_ns=ws[0].start - c["enter_ns"])
            for i, wave in enumerate(ws):
                following = ws[i + 1].start if i + 1 < len(ws) else c["return_ns"]
                need(wave.start <= wave.end <= following, "overlapping manager intervals")
                tier = "cpu" if wave.site[2] < 25 else "cuda"
                d[tier + "_gaps_ns"] += following - wave.end
                d[tier + "_waves"] += 1
                d["manager_ns"] += wave.end - wave.start
            need(
                d["entry_ns"] >= 0
                and d["manager_ns"] == baseline.remap
                and sum(d[k] for k in ("entry_ns", "manager_ns", "cpu_gaps_ns", "cuda_gaps_ns"))
                == span,
                "call wall partition",
            )
            if num <= 2:
                old = prefill["journals"][label]["calls"][num - 1]
                need(
                    old["call"] == num and old["entry_ns"] == d["entry_ns"], "prefill entry control"
                )
                for short, tier in (("cpu", "CPU"), ("cuda", "CUDA0")):
                    values = [v for k, v in old["classes"].items() if k.startswith(tier + "_")]
                    need(
                        sum(v["gap_ns"] for v in values) == d[short + "_gaps_ns"]
                        and sum(v["waves"] for v in values) == d[short + "_waves"],
                        "prefill wave census",
                    )
            groups = [v for (n, _, _), v in jobs.items() if n == num]
            all_jobs = [p for group in groups for p in group]
            # Work/4 and longest job. Collapse all layer barriers within a call for the first bound.
            d["service_call_relaxed_ns"] = (native["layer_fourths"](all_jobs) + 3) // 4
            d["service_layer_release_ns"] = (
                sum(native["layer_fourths"](g) for g in groups) + 3
            ) // 4
            need(
                d["service_call_relaxed_ns"] <= d["service_layer_release_ns"] <= span,
                "worker floor versus measured service envelope",
            )
            d.update(span_ns=span, generations=len(all_jobs))
            phases[phase].update(d)
        need(
            phase_calls == {"prefill": 2, "decode_before_final": 44, "decode_tail": 2}
            and sum(d["generations"] for d in phases.values()) == 2354
            and sum(d["cpu_waves"] + d["cuda_waves"] for d in phases.values()) == 2987,
            "full service conservation",
        )
        exterior, observed = auth["outside_calls_ns"], {"first_final": first, "decode": decode}
        for metric, involved in PHASES.items():
            need(
                sum(phases[k]["span_ns"] for k in involved) + exterior[metric] == observed[metric],
                "observed clock reconstruction",
            )
        policies = {
            "cpu_following_gaps": {p: d["cpu_gaps_ns"] for p, d in phases.items()},
            "all_outside_remap": {p: d["span_ns"] - d["manager_ns"] for p, d in phases.items()},
        }
        bounds = {
            policy: price(observed, credits, exterior) for policy, credits in policies.items()
        }
        floors = {
            release: {
                metric: dict(
                    native_ns=sum(phases[p][release] for p in involved),
                    full_client_ns=exterior[metric] + sum(phases[p][release] for p in involved),
                )
                for metric, involved in PHASES.items()
            }
            for release in ("service_call_relaxed_ns", "service_layer_release_ns")
        }
        traces[label] = dict(
            trajectory_sha256=auth["trajectory_sha256"],
            journal_sha256=auth["journal_sha256"],
            manifest_sha256=auth["manifest_sha256"],
            observed_ns=observed,
            outside_ns=exterior,
            phases=phases,
            generations_by_consumer=Counter(tags.values()),
            bounds=bounds,
            four_worker_service_floors=floors,
        )
    need(
        traces["P97"]["trajectory_sha256"] == traces["P106"]["trajectory_sha256"],
        "different nominal histories",
    )
    return dict(
        schema="tesy-ideal-expert-executor-v1",
        classification="TRACE_DERIVED_CONDITIONAL",
        protocol_sha256=METHOD,
        program_sha256=sha(Path(__file__)),
        traces=traces,
        natural=nested_client(family / "cpu_wave/decision.json"),
        limits_ns=LIMITS,
        model_loads=0,
        new_http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=HERE.parents[3])
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        need(sha(HERE / "operator-protocol.md") == METHOD, "prospective protocol")
        report = analyse(a.repo, a.archive)
    except Exception as exc:
        missing = isinstance(exc, FileNotFoundError) and Path(
            exc.filename
        ).resolve().is_relative_to(a.archive.resolve())
        report = dict(
            classification="NOT_RUN_RAW_REQUIRED" if missing else "FAIL_PRESERVED", reason=str(exc)
        )
    with (a.new_output_dir / "bound.json").open("x") as f:
        json.dump(report, f, indent=2, allow_nan=False, sort_keys=True)
        f.write("\n")
    print(report["classification"], report.get("reason", ""))
    raise SystemExit(report["classification"] != "TRACE_DERIVED_CONDITIONAL")
