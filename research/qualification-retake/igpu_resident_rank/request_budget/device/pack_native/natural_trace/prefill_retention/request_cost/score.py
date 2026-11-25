"""Reopen the two packed P observations and bound free T1-bank delivery at fixed routing."""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = run_path(str(HERE.parent / "evaluate.py"))
T, CHAIN = Q["T"], Q["CHAIN"]
RELEASE, NATIVE = CHAIN["RELEASE"], CHAIN["NATURAL"]
CLIENT = run_path(str(HERE.parents[1] / "client_cut.py"))
check, pinned, digest = Q["check"], Q["pinned"], Q["digest"]
key, origin = RELEASE["identity"], RELEASE["origin"]
SOURCES = {
    "P106": (
        "tesy-full-prefix-natural-physical-20261125-r01",
        "90750b0ccf87d7f5ceb6d89b6b320e1bf9cf07c0082c1961a31f14b67326aee9",
        "d54f29ed903b5dbc772af42be9bd489dc15b2e9819de8cb8ac8b4dea7988a89d",
    ),
    "P97": (
        "tesy-c281-pack-observer-natural-20261125-r01",
        Q["P97"],
        "a649b2e520fcbcc9c8897e4465f85fa6bb38504ab11a5189e71ded47a2ba9309",
    ),
}
PROTOCOL = "9bfa2a760e8c5b605b3d70e8e84f9bb2ce5d85ee316e586aba533d2589aea3e3"
ALLOW = (47_000_000_000 + 5) // 6


@dataclass
class Wave:
    site: tuple
    start: int
    start_drained: bool
    end: int = 0
    end_drained: bool = False
    reserved: set = field(default_factory=set)
    demands: set = field(default_factory=set)
    required_service: dict = field(default_factory=dict)


def timeline(rows):
    waves = []
    jobs = defaultdict(list)
    releases = {}
    active = None
    loading = fifo = claims = 0
    for r in rows:
        k = key(r)
        if r.kind == 5:
            check(r.a == 2 and r.b == 0, "READY initial slot, no claim")
        elif r.kind == 6 and r.b == 1:
            raise ValueError("inherited FIFO")
        elif r.kind == 9:
            check(active is None, "nested remap")
            active = Wave(origin(r), r.ns, (loading, fifo, claims) == (0, 0, 0))
        elif r.kind == 10:
            check(active and origin(r) == active.site, "demand outside its wave")
            active.demands.add(k)
        elif r.kind == 11:
            check(active and active.site == origin(r) and k not in releases, "reservation lineage")
            releases[k] = r
            active.reserved.add(k)
            loading += 1
        elif r.kind == 12:
            fifo += 1
        elif r.kind == 13:
            fifo -= 1
            claims += 1
        elif r.kind == 14:
            fifo -= 1
        elif r.kind in (18, 28):
            raise ValueError("failed or cancelled service")
        elif r.kind == 17:
            loading -= 1
            claims -= 1
        elif r.kind == 23:
            check(active and active.site == origin(r), "mismatched remap end")
            active.end, active.end_drained = r.ns, (loading, fifo, claims) == (0, 0, 0)
            waves.append(active)
            active = None
        if r.kind in (13, 30, 16, 17):
            jobs[k].append(r)
        check(min(loading, claims, fifo) >= 0 and claims <= 4, "worker/queue occupancy")
    check(active is None and loading == fifo == claims == 0, "final drain")
    check(releases.keys() == jobs.keys() and len(jobs) == 2354, "job population")
    prices = {}
    for k, events in jobs.items():
        check(all(origin(r) == origin(releases[k]) for r in events), "worker origin")
        prices[k] = RELEASE["price"](events, releases[k].ns, events[-1].ns)[1]
    for wave in waves:
        for k in wave.reserved & wave.demands:
            check(
                wave.start <= releases[k].ns <= jobs[k][-1].ns <= wave.end,
                "demanded generation outside release/use span",
            )
            wave.required_service[k] = prices[k]
    return waves, {k: origin(r) for k, r in releases.items()}


def expert(generation):
    return generation[0], generation[3]


def phase(call):
    return "prefill" if call <= 2 else ("decode_first" if call <= 46 else "decode_tail")


def bound(waves, bank, use_drain, first_cut):
    """Charge whole eligible non-overlapping spans, less only same-wave compulsory work."""
    phases = defaultdict(Counter)
    exposure = Counter()
    active = False
    distinct = set()
    for w in waves:
        if use_drain and w.start_drained:
            active = False
        hits = {k for k in w.reserved if expert(k) in bank}
        tier = "CPU" if w.site[2] < 25 else "CUDA0"
        s = phases[phase(w.site[0])]
        s["callbacks"] += 1
        s["jobs_" + tier] += len(w.reserved)
        s["hits_" + tier] += len(hits)
        distinct.update(map(expert, hits))
        if active or hits:
            s["direct_callbacks" if hits else "propagated_callbacks"] += 1
            width = w.end - w.start
            floor = RELEASE["four_lanes"](
                [v for k, v in w.required_service.items() if k not in hits]
            )
            check(0 <= floor <= width, "residual floor exceeds the callback")
            s["required_jobs_" + tier] += len(w.required_service.keys() - hits)
            s["callback_ns"] += width
            s["direct_ns" if hits else "propagated_ns"] += width
            s["floor_1x_ns"] += floor
            s["floor_half_ns"] += floor // 2
            if w.site[0] > 46:
                exposure["client_tail_extra_ns"] += max(0, min(w.end, first_cut) - w.start)
            active = True
        if use_drain and w.end_drained:
            active = False
    return phases, len(distinct), exposure["client_tail_extra_ns"]


def adjudicate(phases, first, decode, client_tail, seal_allowance):
    out = {}
    for label, fieldname in (("free", None), ("half", "floor_half_ns"), ("1x", "floor_1x_ns")):
        credit = {
            k: z["callback_ns"] - (z[fieldname] if fieldname else 0) for k, z in phases.items()
        }
        first_gain = credit["prefill"] + credit["decode_first"]
        dec_gain = credit["decode_first"] + credit["decode_tail"]
        first_floor, dec_floor = first - first_gain, decode - dec_gain
        check(min(first_floor, dec_floor) >= 0, "credit exceeds its clock")
        out[label] = {
            "credit_first_ns": first_gain,
            "credit_decode_ns": dec_gain,
            "shared_credit_ns": credit["decode_first"],
            "remaining_first_ns": first_floor,
            "remaining_decode_ns": dec_floor,
            "margin_first_ns": 10**10 - first_floor,
            "margin_decode_ns": ALLOW - dec_floor,
            "first_margin_if_client_tail_free_ns": 10**10 - first_floor + client_tail,
            "first_margin_with_tail_and_all_pre_stream_free_ns": (
                10**10 - first_floor + client_tail + seal_allowance
            ),
            "joint": "HEADROOM_ONLY"
            if first_floor <= 10**10 and dec_floor <= ALLOW
            else "NO_GO_FIXED_SCENARIO",
        }
    return out


def authenticate_raw(root, manifest, files):
    file_map = manifest["files"]
    for rel in files:
        p = root / "ON" / rel
        auth = file_map[f"{root.name}/ON/{rel}"]
        check(p.stat().st_size == auth["bytes"] and digest(p) == auth["sha256"], "raw manifest")


def assess(root, receipt, rows, tiers, banks, selection_allowance):
    host = NATIVE["host_trace"](rows)
    cut = CLIENT["inspect"](root / "ON", receipt, host["calls"])
    check((cut["sample_call"], cut["sample_number"]) == (46, 45), "first final edge")
    first_cut = host["calls"][45]["return_ns"] + cut["last_relevant_return_to_first_final_ns"]
    w, jobs = timeline(rows)
    check(
        [(x.site[0], x.start, x.end) for x in w] == host["callback_spans"]
        and all(a.end <= b.start for a, b in zip(w, w[1:], strict=False)),
        "host callback intervals or order",
    )
    log = root / "ON/raw" / receipt["native_ids"]["raw_stderr_file"]
    check(
        digest(log) == receipt["native_ids"]["stderr_sha256"]
        and T["mapping"](log.read_bytes(), rows)[0] == tiers,
        "current device placement",
    )
    raw = json.loads((root / "ON/raw/T2-result.json").read_bytes())
    pub = receipt["rows"][1]
    first = int(Decimal(str(raw["stream_metrics"]["first_final_content_chunk_s"])) * 10**9)
    decode = int(Decimal(str(raw["timings"]["predicted_ms"])) * 10**6)
    check(
        pub["functional"] == "PASS"
        and pub["cache_n"] == 2044
        and pub["prompt_n"] == 153
        and pub["predicted_n"] == raw["timings"]["predicted_n"] == 47
        and abs(first - pub["first_final_s"] * 10**9) < 2
        and abs(decode - pub["decode_s"] * 10**9) < 2,
        "receipt clocks/trajectory",
    )
    answers = {}
    for name, bank in {"empty": set(), **banks, "all_jobs": set(map(expert, jobs))}.items():
        answers[name] = {}
        for envelope, drained in (("drained", True), ("persistent", False)):
            phases, distinct, extra = bound(w, bank, drained, first_cut)
            estimate = adjudicate(phases, first, decode, extra, selection_allowance)
            answers[name][envelope] = {
                "phases": phases,
                "distinct_hit_keys": distinct,
                "client_tail_extra_ns": extra,
                "cost": estimate,
            }
    return {
        "first_final_ns": first,
        "decode_ns": decode,
        "client_tail_max_ns": cut["last_relevant_return_to_first_final_ns"],
        "callbacks": len(w),
        "jobs": len(jobs),
        "drained_starts": sum(x.start_drained for x in w),
        "drained_ends": sum(x.end_drained for x in w),
        "route": host["route"],
        "pre_stream_allowance_ns": selection_allowance,
        "policies": answers,
    }, jobs


def compare(archive):
    check(digest(HERE / "protocol.md") == PROTOCOL, "frozen protocol")
    roots, provenance = {}, {}
    for label, (name, family_sha, manifest_sha) in SOURCES.items():
        part = archive / ("part-" + label[1:])
        root = part / name
        manifest = pinned(part / "manifest.json", manifest_sha)
        authenticate_raw(root, manifest, ["raw/T2-result.json", "raw/T2-request.jsonl"])
        roots[label] = root
        provenance[label] = {"manifest_sha256": manifest_sha, "family_sha256": family_sha}
    root = roots["P106"]
    sel, rows, tiers, source = Q["read_new"](root, SOURCES["P106"][1])
    banks = {k: set(map(tuple, v["ordered_keys"])) for k, v in sel["banks"].items()}
    check(set(banks) == {"prefill", "lru"} and all(len(b) == 353 for b in banks.values()), "banks")
    new_family = pinned(root / "family.json", SOURCES["P106"][1])
    link = new_family["arms"]["ON"]
    a = pinned(root / "ON/arm.json", link["sha256"])
    receipt = pinned(root / "ON/receipt.json", a["receipt_sha256"])
    start = json.loads((root / "ON/raw/T2-result.json").read_bytes())["request_started_monotonic"]
    allowance = receipt["full_prefix"]["post_entry_ns"][1] - int(Decimal(str(start)) * 10**9)
    check(0 <= allowance <= 15_000_000_000, "pre-stream credit")
    current, current_jobs = assess(root, receipt, rows, tiers, banks, allowance)
    bindings = Q["bindings"](rows)
    del rows
    root = roots["P97"]
    _, _, receipt_old, stored = CHAIN["chain"](root, SOURCES["P97"][1])
    reproduced = NATIVE["audit_arm"](
        root / "ON", receipt_old, receipt_old["pack_events"]["before_second_ns"]
    )
    check(
        json.loads(json.dumps(reproduced)) == stored and stored["jobs"]["eligible_clean_run"],
        "P97 service audit",
    )
    prior_rows, header = T["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
    prior, prior_jobs = assess(root, receipt_old, prior_rows, tiers, banks, 0)
    check(
        current_jobs == prior_jobs
        and Q["bindings"](prior_rows) == bindings
        and current["route"] == prior["route"]
        and receipt_old["trajectories"] == receipt["trajectories"],
        "joint comparison: jobs, entry, route or sampled trajectories",
    )
    return {
        "status": "TRACE_DERIVED_FIXED_RESERVATIONS",
        "protocol_sha256": PROTOCOL,
        "source_sha256": digest(HERE / "score.py"),
        "provenance": provenance,
        "selection": source,
        "P97_journal_sha256": header["journal_sha256"],
        "P106": current,
        "P97": prior,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive", type=Path, required=True)
    cli.add_argument("--new-output-dir", type=Path, required=True)
    a = cli.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = compare(a.archive)
    except Exception as exc:
        tb = exc.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        result = {
            "status": "FAIL_PRESERVED",
            "reason": str(exc),
            "location": [Path(tb.tb_frame.f_code.co_filename).name, tb.tb_lineno],
        }
    with (a.new_output_dir / "receipt.json").open("x") as fd:
        json.dump(result, fd, indent=2, sort_keys=True, allow_nan=False)
        fd.write("\n")
    print(result["status"])
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
