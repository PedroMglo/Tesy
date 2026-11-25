"""Exploratory C135 call-148 upper bounds, reusing the interval solver at PR #45."""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

PIN = "83146dade3f90235775e4a31a8d3d8ccae3476a7"
SOURCES = {
    "research/prefill-slot-proof/critical_intervals.py": "5621f4cba24ff3c2b493d45d9ce1598800dfcc167d341f331cd0d8748fc1d494",  # noqa: E501
    "research/prefill-slot-proof/critical.py": "b7fd73abb2f6651d27f9fab13748f171c78206a88fd6e39f2e68fa64ad1454a7",  # noqa: E501
    "tools/c122_trace_validate.py": "7de57a93f3ac9eb60ae2ae7bc4e1a712b695a4f4ae56fb5e21ce546d3ffb441c",  # noqa: E501
    "tools/c123_analyze_trace.py": "f68f8f5126a33d0286355a664ccfb14292e1f4679a55629b06175fa8b26646ce",  # noqa: E501
    "tools/c2_gate.py": "1e023e2e944907144d8a56a45262a848e7154e413c4d75ff1b089fc4ae2a6d99",
}
TRACE = "91610b12291d5a42a12bba09f5d4ff188d25ee0001ab89e894bdd508005e82fb"
PRODUCT = "f64067231b0936d82ce822ca782adfdb00bb9134b60d46fdc6a5bac3e6d64f74"
PRODUCT_PATH = (
    Path(__file__).resolve().parents[1] / "nvme_conversation/evidence-20261124-r1/evidence.json"
)
CALLBACK = {"DEMAND", "PRELOAD", "RESERVE", "EVICT", "ENQUEUE", "WAIT_BEGIN", "WAIT_END"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def imports(checkout):
    head = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    require(head == PIN, "PR45 HEAD mismatch")
    for name, expected in SOURCES.items():
        require(digest(checkout / name) == expected, f"dependency mismatch: {name}")
    sys.path.insert(0, str(checkout / "research/prefill-slot-proof"))
    import critical
    import critical_intervals

    for name in SOURCES:
        require(
            Path(sys.modules[Path(name).stem].__file__).resolve() == (checkout / name).resolve(),
            name,
        )
    return critical, critical_intervals


def component_times(rows, key_for):
    start = {}
    durations = defaultdict(dict)
    phases = {
        "READ_BEGIN": ("read", True),
        "READ_END": ("read", False),
        "TENSOR_SET_BEGIN": ("set", True),
        "TENSOR_SET_RETURN": ("set", False),
    }
    for row in rows:
        if row["kind"] not in phases:
            continue
        phase, begin = phases[row["kind"]]
        key = key_for(row)
        part = (phase, row["component"])
        ident = (key, part)
        if begin:
            require(ident not in start and part not in durations[key], "duplicate component")
            start[ident] = row["mono_us"]
        else:
            require(ident in start and row["mono_us"] >= start[ident], "unmatched component")
            durations[key][part] = row["mono_us"] - start.pop(ident)
    require(not start, "incomplete component")
    complete = {(phase, part) for phase in ("set", "read") for part in range(3)}
    require(all(d.keys() == complete for d in durations.values()), "missing read or set")
    return {
        k: {p: sum(d[p, i] for i in range(3)) for p in ("read", "set")}
        for k, d in durations.items()
    }


def build_scopes(rows, c):
    candidates, demands, waits, service, enqueue, _, scope_of = c.wave_inputs(rows)
    parts = component_times(rows, c.generation)
    require(service.keys() == parts.keys(), "service/component mismatch")
    first = {}
    last = {}
    resident = {}
    hits = {}
    owner = Counter()
    clock = {r["seq"]: r["mono_us"] for r in rows}
    tile = -1
    prev_layer = 36
    wave = None
    for r in rows:
        kind, layer, slot = r["kind"], r["layer"], (r["layer"], r["slot"])
        if kind == "DEMAND":
            if prev_layer > layer:
                tile += 1
            prev_layer = layer
            wave = tile, layer, r["wave"]
            first.setdefault(wave, r["seq"])
            if r["state"] == 2 and slot in resident:
                key = resident[slot]
                require(key[1] == r["expert"], "resident expert disagrees")
                hits.setdefault(key, wave)
        elif kind in {"EVICT", "RESERVE"}:
            resident.pop(slot, None)
        elif kind == "LOAD_END":
            resident[slot] = c.generation(r)
        if kind in CALLBACK:
            require(wave is not None, "callback outside wave")
            last[wave] = r["seq"]
    waves = list(first)
    end_seq = rows[-1]["seq"]
    next_start = dict(zip(waves, [first[w] for w in waves[1:]] + [end_seq], strict=True))
    deadline = {}
    for w, jobs in demands.items():
        for _, key in jobs:
            require(key not in deadline, "duplicate demand")
            deadline[key] = waits[w][-1]["seq"]
    for key, w in hits.items():
        if scope_of[key] == w[:2]:
            limit = waits[w][-1]["seq"] if w in waits else next_start[w]
            deadline[key] = min(limit, deadline.get(key, limit))
    scopes = {}
    for w in waves:
        s = w[:2]
        if s not in scopes:
            scopes[s] = {"jobs": [], "waits": [], "callbacks": [], "begin": first[w]}
        scopes[s]["end"] = next_start[w]
        scopes[s]["callbacks"].append((first[w], last[w]))
        if w in waits:
            a, b = waits[w]
            scopes[s]["waits"].append((a["seq"], b["seq"]))
            owner[w[2]] += b["mono_us"] - a["mono_us"]
    require(set(deadline) == set(service), "missing first consumer")
    for k, duration in service.items():
        scope = scopes[scope_of[k]]
        r, d = enqueue[k][0], deadline[k]
        require(scope["begin"] <= r < d <= scope["end"], "job escaped scope")
        require(parts[k]["read"] + parts[k]["set"] <= duration, "component span exceeds service")
        scope["jobs"].append((k, r, d, duration, parts[k]))
    return [s for s in scopes.values() if s["jobs"]], clock, owner, candidates


def ceilings(
    scopes, clock, earliest_end, *, advance=False, free_sets=False, read_ppm=0, removed=None
):
    total_fixed = total_free = 0
    for s in scopes:
        if removed is not None and not any(k in removed for k, *_ in s["jobs"]):
            continue
        begin, end = s["begin"], s["end"]
        points = {begin, end}
        pairs = set(s["waits"])
        for a, b in pairs:
            points.update((a, b))
        jobs = []
        for k, r, d, duration, parts in s["jobs"]:
            if removed is not None and k in removed:
                continue
            release = begin if advance else r
            service = duration - (parts["set"] if free_sets else 0)
            # Round discounted READ service down, favourable to the candidate.
            service -= (parts["read"] * read_ppm + 999_999) // 1_000_000
            jobs.append((release, d, service))
            points.update((release, d))
        observed = clock[end] - clock[begin]
        fixed = earliest_end({n: clock[n] for n in points}, pairs, jobs)
        require(fixed <= observed + 1, "historical scope inconsistent")
        total_fixed += min(observed + 1 - fixed, sum(clock[b] - clock[a] + 1 for a, b in pairs))
        for a, b in s["callbacks"]:
            points.update((a, b))
        seqs = sorted(points)
        free_pairs = {
            (a, b)
            for a, b in zip(seqs, seqs[1:], strict=False)
            if any(x <= a < b <= y for x, y in s["callbacks"])
        }
        free = earliest_end({n: clock[n] for n in points}, free_pairs, jobs)
        require(free <= observed + 1, "callback sensitivity inconsistent")
        total_free += min(
            observed + 1 - free, sum(clock[b] - clock[a] + 1 for a, b in s["callbacks"])
        )
    return {"outside_wait_fixed_us": total_fixed, "observed_callbacks_free_us": total_free}


def analyse(checkout, path):
    c, ci = imports(checkout)
    require(path.stat().st_size == 3603647 and digest(path) == TRACE, "C135 input mismatch")
    require(digest(PRODUCT_PATH) == PRODUCT, "natural C281 receipt mismatch")
    product = json.loads(PRODUCT_PATH.read_text(), parse_float=Decimal)["rows"][1]
    require((product["id"], product["prompt_n"]) == ("c112-repeat", 153), "product workload")
    scale = int(
        ((product["first_final_s"] - product["decode_s"] - 10) * 10**6).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    c.validate(path)
    _, all_rows = c.trace_rows(path)
    rows = [r for r in all_rows if r["call_id"] == 2]
    scopes, clock, by_wave, candidates = build_scopes(rows, c)
    require((rows[0]["kind"], rows[-1]["kind"]) == ("CALL_BEGIN", "CALL_END"), "call not closed")
    ref = ci.interval_report(all_rows)

    def bound(**kwargs):
        return ceilings(scopes, clock, ci.earliest_end, **kwargs)

    crosscheck = bound(removed=candidates)
    require(
        crosscheck
        == {
            "outside_wait_fixed_us": ref["interval_capacity_saving_upper_us"],
            "observed_callbacks_free_us": ref["free_observed_callback_saving_upper_us"],
        },
        "PR45 reproduction mismatch",
    )
    low, high = 0, 1_000_000
    while high - low > 1:
        mid = (low + high) // 2
        if bound(read_ppm=mid)["outside_wait_fixed_us"] >= scale:
            high = mid
        else:
            low = mid
    at, before = bound(read_ppm=high), bound(read_ppm=low)
    require(
        before["outside_wait_fixed_us"] < scale <= at["outside_wait_fixed_us"],
        "threshold not bracketed",
    )
    totals = defaultdict(Counter)
    for s in scopes:
        for k, _, _, duration, parts in s["jobs"]:
            tier = "CPU" if k[0] < 25 else "CUDA0"
            totals[tier].update(parts)
            totals[tier].update(jobs=1, total_service=duration)
    return {
        "class": "TRACE_DERIVED_EXPLORATORY",
        "c135_sha256": TRACE,
        "c135_bytes": path.stat().st_size,
        "c281_sha256": PRODUCT,
        "pr45_commit": PIN,
        "source_sha256": SOURCES,
        "call": 2,
        "scope_count_with_loads": len(scopes),
        "sum_service_worker_us_by_tier": dict(totals),
        "observed_wait_wall_us_by_wave": dict(by_wave),
        "cross_campaign_scale_ceil_us": scale,
        "crosscheck_remove_184": crosscheck,
        "original_enqueue": bound(),
        "first_demand": bound(advance=True),
        "free_sets_original_enqueue": bound(free_sets=True),
        "read_service_threshold_original_enqueue": {
            "discount_ppm": high,
            "ceiling": at,
            "previous_ppm": low,
            "previous_ceiling": before,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr45-checkout", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.new_output_dir
    out.mkdir(exist_ok=False)
    try:
        result = analyse(args.pr45_checkout.resolve(), args.trace)
        pending = out / "receipt.pending"
        pending.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        pending.rename(out / "receipt.json")
    except Exception as exc:
        (out / "FAIL.json").write_text(
            json.dumps({"error": type(exc).__name__, "detail": str(exc)}) + "\n"
        )
        raise


if __name__ == "__main__":
    main()
