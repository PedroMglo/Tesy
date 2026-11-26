"""C295 fixed-service critical path with free, unlimited retention of completed reads."""

import argparse
import hashlib
import json
import math
import resource
import signal
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
ROOT = UNIT.parents[1]
sys.path[:0] = [str(UNIT), str(ROOT / "tools")]
import expert_prediction_scenario as c295  # noqa: E402
from l2_read_admission import screen as admission  # noqa: E402
from prefill_causal import plan as prefix  # noqa: E402

require = admission.require
SCENARIO = "abc2644482869d77d1acb802ec541945c8588ccfb264ed6a9981415a351990fc"
C295 = "0e63bb384249c740f7ccb48ec088d56c53f4e46647a42d16a410b85c489f127a"
BUDGET_US = 32_000_000 / 6
ARENA = 128 * 2**20


def eligible(rows):
    published, active, hits, starts = set(), {}, set(), set()
    counts = Counter()
    for r in rows:
        if r["kind"] not in (5, 10):
            continue
        key = (r["layer"], r["expert"])
        w = (*key, r["slot"], r["gen"])
        if r["kind"] == 5:
            require(w not in starts and key not in active, "concurrent or repeated generation")
            starts.add(w)
            active[key] = w
            if r["call"] > 0:
                counts["decode_claims"] += 1
                if key in published:
                    hits.add(w)
        else:
            require(active.pop(key, None) == w, "publication identity")
            published.add(key)
    require(not active, "unfinished services")
    return hits, counts["decode_claims"]


def maxima(data, hits):
    jobs, groups, tail, _, initial, late, _ = data
    require(not initial and not late, "outstanding service at decode entry")
    expected = {w for w, j in jobs.items() if j["owner"] > 0}
    require(hits <= expected, "hit outside decode")
    seen = set()
    fixed = tail
    stats = Counter()
    tiers = {"CPU": Counter(), "CUDA0": Counter()}
    for g in groups:
        fixed += g["pre"] + g["attention"] + g["after"]
        keys = g["need"]
        require(
            len(keys) <= 4 and len(keys) == len(set(keys)) and not set(keys) & seen,
            "overlapping groups",
        )
        require(
            all(
                w in expected and w[0] == g["layer"] and jobs[w]["owner"] == g["call"] for w in keys
            ),
            "foreign job",
        )
        seen.update(keys)
        if not keys:
            stats["groups_without_service"] += 1
            continue
        old = {w: jobs[w]["read"] + jobs[w]["copy"] for w in keys}
        new = {w: old[w] if w not in hits else jobs[w]["copy"] for w in keys}
        a, b = max(old.values()), max(new.values())
        before = {w for w in keys if old[w] == a}
        after = {w for w in keys if new[w] == b}
        values = Counter(
            service_groups=1,
            old_max_us=a,
            new_max_us=b,
            saved_wall_us=a - b,
            hit_worker_read_us=sum(jobs[w]["read"] for w in keys if w in hits),
            hits=len(set(keys) & hits),
            claims=len(keys),
            gates_advanced=int(a > b),
            changed_last_set=int(before != after),
            previous_last_no_longer_last=len(before - after),
            last_has_cold_read_after=int(bool(after - hits)),
            last_only_hits_after=int(not (after - hits)),
        )
        stats.update(values)
        tiers["CPU" if g["layer"] < 25 else "CUDA0"].update(values)
    require(seen == expected, "unserved decode generation")
    return fixed, stats, tiers


def arm(raw, name, historical):
    _, proof = admission.service_arm(raw, name)
    path = raw / (name + ".native") / "events.tsv"
    rows = c295.events(path, True)
    hits, n = eligible(rows)
    data = c295.extract(rows)
    require(
        [(g["call"], g["layer"]) for g in data[1]]
        == [(call, layer) for call in range(1, 33) for layer in range(36)],
        "all call/layer groups",
    )
    fixed, s, t = maxima(data, hits)
    require(s["claims"] == n == (1081 if "nominal" in name else 1308), "R0 job conservation")
    cheaper = {w: {**j, "read": 0.0 if w in hits else j["read"]} for w, j in data[0].items()}
    require([h["scale"] for h in historical] == [0.8, 1.0, 1.2], "service scales")
    scales = []
    for h in historical:
        k = h["scale"]
        base = c295.simulate(data, None, k, ARENA)
        require(base == h["baseline"], "sealed C295 baseline")
        if k == 1.0:
            require(abs(base["decode_us"] - data[3]) <= 0.05 * data[3], "C295 observed clock drift")
        variant = c295.simulate((cheaper, *data[1:]), None, k, ARENA)
        a, b = base["decode_us"], variant["decode_us"]
        require(
            math.isclose(a, fixed + k * s["old_max_us"], rel_tol=0, abs_tol=1e-4)
            and math.isclose(b, fixed + k * s["new_max_us"], rel_tol=0, abs_tol=1e-4),
            "independent group maximum differs",
        )
        scales.append(
            {
                "scale": k,
                "observed_decode_us": data[3],
                "baseline_us": a,
                "ideal_us": b,
                "saved_us": a - b,
                "saved_fraction": (a - b) / a,
                "necessary_fraction": (a - BUDGET_US) / a,
                "ideal_steps_per_s": 32e6 / b,
                "remaining_slack_us": BUDGET_US - b,
                "reaches_6": b <= BUDGET_US,
            }
        )
    return {
        "source_sha256": proof["source_sha256"],
        "initial_inflight": 0,
        "fixed_nonservice_us": fixed,
        "service_at_scale_1": s,
        "tiers_at_scale_1": t,
        "scales": scales,
    }


def run(raw):
    prefix.read_pinned(Path(c295.__file__), C295)
    path = ROOT / "results/c295-activation-byte-optimistic-scenario-20261006/scenario.json"
    prior = json.loads(prefix.read_pinned(path, SCENARIO))
    arms = {}
    for case, values in prior["cases"].items():
        require([v["run"] for v in values] == [f"c294-{case}-{i}-on" for i in (2, 3)], "arm pair")
        for v in values:
            arms[v["run"]] = arm(raw, v["run"], v["service_sensitivity"])
    require(set(arms) == set(admission.boundary.NAMES), "four arms")
    case_gates = {}
    for case in prior["cases"]:
        pair = [arms[f"c294-{case}-{i}-on"] for i in (2, 3)]
        case_gates[case] = [
            {
                "scale": scale,
                "both_reach_6": all(arm["scales"][index]["reaches_6"] for arm in pair),
                "neither_reaches_6": all(not arm["scales"][index]["reaches_6"] for arm in pair),
            }
            for index, scale in enumerate((0.8, 1.0, 1.2))
        ]
    return {
        "status": "PASS_CONDITIONAL_SCENARIO",
        "case_gates": case_gates,
        "scope": "INFINITE_L2_FIXED_SERVICE_C295_SUPPLIED_DECODE",
        "budget_us": BUDGET_US,
        "arms": arms,
        "C295_sha256": C295,
        "scenario_sha256": SCENARIO,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    require(not a.new_output_dir.resolve().is_relative_to(a.raw_dir.resolve()), "protect raw")
    cap = 512 * 2**20
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (min(cap, hard) if hard >= 0 else cap, hard))

    def expired(*_):
        raise TimeoutError("120s envelope")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(120)
    commit = prefix.git(HERE, "rev-parse", "HEAD")
    tree = prefix.git(HERE, "rev-parse", "HEAD^{tree}")
    clean = not prefix.git(
        HERE,
        "-c",
        "core.preloadIndex=false",
        "-c",
        "index.threads=1",
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
    )
    a.new_output_dir.mkdir(mode=0o700)
    try:
        require(clean, "dirty measurement checkout")
        result = run(a.raw_dir)
    except (OSError, KeyError, TypeError, ValueError, IndexError, MemoryError) as exc:
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(exc),
        }
    result.update(
        commit=commit,
        tree=tree,
        clean=clean,
        program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as f:
        f.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(result["status"])
    return int("arms" not in result)


if __name__ == "__main__":
    sys.exit(main())
