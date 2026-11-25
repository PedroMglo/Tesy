"""R0 historical lower bounds after granting one free full component per generation."""
import argparse
import hashlib
import json
import math
import resource
import signal
import sys
from collections import defaultdict
from pathlib import Path

PROTOCOL = "9cdf384fdfaadde16989183d118f72537be10c07fc0bd2ccf38e170a538a733c"
PREFILL = "f2cd36d9b060e4864de620aab05013fe462b9a581b86474a3d127abd1b66c8cf"
DECODE = "3473a9506fbb4d4e2e5051b243e9cbce04c76ecb96707a5c0fd3e1628d11eebe"
SCENARIO = "abc2644482869d77d1acb802ec541945c8588ccfb264ed6a9981415a351990fc"
COMP = 4_406_400
PREFILL_BUDGET = 2_427_104
DECODE_BUDGET = 32e6 / 6


def require(ok, cause):
    if not ok:
        raise ValueError(cause)


def pinned(path, identity):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == identity, "digest " + path.name)
    return data


def reduced(values):
    require(len(values) == 3 and min(values) >= 0, "three serial READ durations")
    return sum(max(0, d - 1) for d in sorted(values)[:2])


def prefill(trace, original):
    import c123_analyze_trace as c123

    require(trace.stat().st_size == 3603647, "C135 trace length")
    pinned(trace, original["trace_sha256"])
    c123.validate(trace)
    layers, rows = c123.trace_rows(trace)
    require(all(x["bytes"] == 3 * COMP for x in layers.values()), "R0 expert payload")
    calls = []
    for call, old in enumerate(original["calls"], 1):
        values = defaultdict(dict)
        commits = set()
        span = {}
        for r in rows:
            if r["call_id"] != call:
                continue
            kind = r["kind"]
            w = tuple(r[k] for k in ("layer", "expert", "slot", "generation"))
            if kind in ("CALL_BEGIN", "CALL_END"):
                span[kind] = r["mono_us"]
            if kind == "LOAD_END":
                require(w not in commits, "duplicate load")
                commits.add(w)
            if kind in ("READ_BEGIN", "READ_END"):
                k = (r["component"], kind)
                require(r["logical_bytes"] == COMP and k not in values[w], "C135 component")
                values[w][k] = r["mono_us"]
        require(len(values) == old["jobs"] and set(values) == commits, "C135 generations")
        require(span["CALL_END"] - span["CALL_BEGIN"] == old["observed_call_us"], "call clock")
        components = [0, 0, 0]
        sums = {"CPU": 0, "CUDA0": 0}
        for w, edges in values.items():
            stamps = [edges[i, op] for i in range(3) for op in ("READ_BEGIN", "READ_END")]
            require(len(edges) == 6 and stamps == sorted(stamps)
                    and span["CALL_BEGIN"] <= stamps[0] <= stamps[-1] <= span["CALL_END"],
                    "READ ownership and containment in original call")
            durations = [b - a for a, b in zip(stamps[::2], stamps[1::2], strict=True)]
            for i, d in enumerate(durations):
                components[i] += d
            sums[layers[w[0]]["device"]] += reduced(durations)
        require(sum(components) == old["read_worker_us"], "C135 raw worker-time")
        calls.append(dict(call=call, tokens=old["tokens"], jobs=len(commits),
                          all_read_worker_us_by_component=components,
                          remaining_worker_us_by_tier=sums, floor_us=sum(sums.values()) / 4))
    n = sum(c["jobs"] for c in calls)
    require(n == 1222, "C135 admissions")
    total = sum(c["floor_us"] for c in calls)
    allowed = PREFILL_BUDGET * 4500
    return dict(calls=calls, floor_us=total, budget_us=PREFILL_BUDGET,
                exceeds_budget=total > PREFILL_BUDGET, trace_sha256=original["trace_sha256"],
                payload=n * 3 * COMP, down_payload=n * COMP, allowed_bytes_at_4_5_GB_s=allowed,
                required_fraction_down=(n * 3 * COMP - allowed) / (n * COMP))


def decode(raw, name, sealed, historical):
    import expert_prediction_scenario as c295

    for f, identity in sealed["raw_sha256"].items():
        pinned(raw / (name + ".native") / f, identity)
    rows = c295.events(raw / (name + ".native") / "events.tsv", True)
    jobs, groups, tail, observed, initial, late, t0 = c295.extract(rows)
    require(not initial and not late, "outstanding service at first decode")
    durations = defaultdict(dict)
    for r in rows:
        if r["call"] <= 0 or r["kind"] not in (6, 7):
            continue
        w = tuple(r[k] for k in ("layer", "expert", "slot", "gen"))
        edge = (r["component"], r["kind"])
        require(edge not in durations[w] and r["bytes"] == COMP, "C294 component")
        durations[w][edge] = r["us"]
    require(set(durations) == {w for w, j in jobs.items() if j["owner"] > 0}, "decode ownership")
    changed = dict(jobs)
    component_sums = [0, 0, 0]
    for w, cc in durations.items():
        d = [cc[c, 7] - cc[c, 6] for c in range(3)]
        require(len(cc) == 6 and sum(d) == jobs[w]["read"], "C294 serial service")
        changed[w] = {**jobs[w], "read": reduced(d), "copy": 0}
        for i, v in enumerate(d):
            component_sums[i] += v
    require([(g["call"], g["layer"]) for g in groups] ==
            [(call, layer) for call in range(1, 33) for layer in range(36)], "decode population")
    seen = set()
    tiers = {}
    for tier, is_cpu in (("CPU", True), ("CUDA", False)):
        pure = control = n = 0
        for g in groups:
            if (g["layer"] < 25) != is_cpu:
                continue
            keys = g["need"]
            require(len(keys) <= 4 and len(keys) == len(set(keys)) and not seen.intersection(keys)
                    and all(w[0] == g["layer"] and jobs[w]["owner"] == g["call"] for w in keys),
                    "generation consumed by nonoverlapping group")
            seen.update(keys)
            n += len(keys)
            pure += max((changed[w]["read"] for w in keys), default=0)
            control += max((sum(max(0, durations[w][c, 7] - durations[w][c, 6] - 1)
                                for c in range(3)) for w in keys), default=0)
        old = sealed["tiers"][tier]
        require((n, control) == (old["misses"], old["read_floor_us"]), "prior read-only floor")
        tiers[tier] = dict(jobs=n, pure_floor_us=pure, R0_pure_floor_us=control,
                           remaining_logical_bytes=2 * COMP * n)
    require(seen == set(durations), "missing decode input")
    pure = sum(x["pure_floor_us"] for x in tiers.values())
    fixed = tail + sum(g["pre"] + g["attention"] + g["after"] for g in groups)
    scales = []
    require([x["scale"] for x in historical] == [0.8, 1, 1.2], "C295 sensitivity")
    for h in historical:
        scale = h["scale"]
        base_data = (jobs, groups, tail, observed, initial, late, t0)
        require(c295.simulate(base_data, None, scale, 128 << 20) == h["baseline"], "C295 baseline")
        simulated = c295.simulate((changed, *base_data[1:]), None, scale, 128 << 20)["decode_us"]
        require(math.isclose(simulated, fixed + scale * pure, rel_tol=0, abs_tol=1e-4),
                "independent C295 group wall")
        scales.append(dict(scale=scale, pure_floor_us=scale * pure, fixed_plus_read_us=simulated,
                           pure_exceeds_budget=scale * pure > DECODE_BUDGET,
                           fixed_plus_read_exceeds_budget=simulated > DECODE_BUDGET))
    return dict(tiers=tiers, all_read_worker_us_by_component=component_sums,
                C295_fixed_nonservice_us=fixed, scales=scales, raw_sha256=sealed["raw_sha256"])


def run(repo, trace, raw):
    unit = repo / "research/qualification-retake"
    sys.path.insert(0, str(repo / "tools"))
    pinned(Path(__file__).with_name("protocol.md"), PROTOCOL)
    old_pre = json.loads(pinned(unit / "prefill_read_floor/replay-r2/receipt.json", PREFILL))
    old_dec = json.loads(pinned(unit / "component_ready_bound/evidence/receipt.json", DECODE))
    scenario = json.loads(pinned(repo / "results/c295-activation-byte-optimistic-scenario-20261006"
                                 / "scenario.json", SCENARIO))
    required = {f"c294-{case}-{r}-on" for case in ("nominal153", "code153") for r in (2, 3)}
    arms = {}
    for records in scenario["cases"].values():
        for h in records:
            name = h["run"]
            arms[name] = decode(raw, name, old_dec["arms"][name], h["service_sensitivity"])
    require(set(arms) == required, "four C294 arms")
    return dict(status="REPRODUCED_CONDITIONAL_FIXED_REMAINING_READS", protocol_sha256=PROTOCOL,
                program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                prefill=prefill(trace, old_pre), decode_budget_us=DECODE_BUDGET, decode=arms)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "trace", "raw-dir", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (384 << 20, 384 << 20))
    signal.alarm(120)
    require(not a.new_output_dir.resolve().is_relative_to(a.raw_dir.resolve()) and
            not a.new_output_dir.resolve().is_relative_to(a.trace.resolve().parent), "raw overlap")
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    out = a.new_output_dir / "receipt.json"
    try:
        receipt = run(a.repo.resolve(), a.trace, a.raw_dir)
    except Exception as exc:
        out.write_text(json.dumps({"status": "FAIL_PRESERVED", "error": str(exc)}) + "\n")
        raise
    out.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
