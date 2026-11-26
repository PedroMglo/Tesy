"""C294/C295 conditional decode floor with 378 L2 entries and free primary CPU SET."""

import argparse
import hashlib
import json
import math
import os
import resource
import signal
import sys
from collections import Counter
from pathlib import Path

PRIOR = "3f1f4c2760554a1f8b074dde4309da23a5bf7cbd5a3029586f0d48bb6679b6dd"
PROTOCOL = "b1b38f74b110dac571c77887c9445df1215f91d006ccb41c7a8a8605ae7d4455"
CAP = 378
PAYLOAD = 13_219_200
SCALES = (0.8, 1.0, 1.2)
TIERS = ("CPU", "CUDA0")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def pinned(path, digest):
    data = path.read_bytes()
    need(hashlib.sha256(data).hexdigest() == digest, "source digest: " + path.name)
    return data


def sanitized_hash(obj):
    return hashlib.sha256(
        json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def measured_components(rows, jobs):
    """Reconstruct the serial READ/SET chain for each unique decode generation."""
    recorded = {}
    for row in rows:
        kind = row["kind"]
        if row["call"] <= 0 or kind not in range(5, 11):
            continue
        key = tuple(row[x] for x in ("layer", "expert", "slot", "gen"))
        job = jobs[key]
        need(row["call"] == job["owner"], "C295 job owner")
        component = row["component"] if kind in (6, 7, 8, 9) else -1
        item = (kind, component)
        chunk = recorded.setdefault(key, {})
        need(item not in chunk, "duplicate component edge")
        chunk[item] = row["us"]
    expected = {w for w, j in jobs.items() if j["owner"] > 0}
    need(expected == recorded.keys(), "missing generation")
    split = {}
    subtotals = {t: Counter() for t in TIERS}
    for w, cc in recorded.items():
        order = (
            [(5, -1)] + [(p, c) for c in range(3) for p in (6, 7, 8, 9)] + [(10, -1)]
        )
        need(set(order) == cc.keys(), "missing component")
        times = [cc[k] for k in order]
        need(times == sorted(times), "per-generation component chain")
        read = sum(cc[7, c] - cc[6, c] for c in range(3))
        copy = sum(cc[9, c] - cc[8, c] for c in range(3))
        residual = times[-1] - times[0] - read - copy
        j = jobs[w]
        need(
            (j["begin"], j["end"], j["read"], j["copy"])
            == (times[0], times[-1], read, copy + residual)
            and min(read, copy, residual) >= 0,
            "P5–P10 conservation",
        )
        split[w] = (read, copy, residual)
        subtotals[TIERS[w[0] >= 25]].update(
            jobs=1, read_worker_us=read, set_worker_us=copy, other_worker_us=residual
        )
    return split, subtotals


def adjust(data, split, treatment):
    updated = {}
    for w, j in data[0].items():
        if j["owner"] > 0 and w[0] < 25:
            read, copy, other = split[w]
            j = {
                **j,
                "copy": {
                    "control": copy + other,
                    "free_cpu_set": other,
                    "free_cpu_set_and_residual": 0,
                }[treatment],
            }
            need(j["read"] == read, "read duration changed")
        updated[w] = j
    return updated, *data[1:]


def arm(base, raw, name, old, historical):
    cold = base.cold
    jobs, proof = cold.admission.service_arm(raw, name)
    need(
        proof["source_sha256"] == old["raw_sha256"]
        and proof["primary_I_sha256"] == old["I_sha256"],
        "arm provenance/entry",
    )
    rows = cold.c295.events(raw / (name + ".native") / "events.tsv", True)
    claims = base.claim_index(rows, jobs)
    data = cold.c295.extract(rows)
    need(
        set(claims.values()) == {w for w, j in data[0].items() if j["owner"] > 0}
        and len(claims) == old["decode_claims"]
        and len(jobs["increment"]) == old["increment_publications"]
        and [(g["call"], g["layer"]) for g in data[1]]
        == [(call, layer) for call in range(1, 33) for layer in range(36)],
        "unmatched phase or routing",
    )
    split, subtotal = measured_components(rows, data[0])
    need(tuple(h["scale"] for h in historical) == SCALES, "C295 scale menu")
    for h in historical:
        need(
            cold.c295.simulate(data, None, h["scale"], cold.ARENA) == h["baseline"],
            "native C295 control",
        )
    previous = old["eligibility"]["any"]["by_capacity"][str(CAP)]
    out = {
        "prior_control_us": {
            str(h["scale"]): h["baseline"]["decode_us"] for h in historical
        },
        "raw_sha256": old["raw_sha256"],
        "P_sha256": old["P_sha256"],
        "I_sha256": old["I_sha256"],
        "F_sha256": old["F_sha256"],
        "decode_ranks_sha256": old["decode_ranks_sha256"],
        "phase_decode_worker_sums_us": subtotal,
        "cases": {},
    }
    latest = {}
    for mode in ("control", "free_cpu_set", "free_cpu_set_and_residual"):
        service = adjust(data, split, mode)
        groups = [
            [
                (w[:2], int(service[0][w]["read"]), int(service[0][w]["copy"]))
                for w in g["need"]
            ]
            for g in service[1]
        ]
        optimum = base.solver.solve(jobs, groups, None, [CAP])[CAP]
        for typ in ("optimistic", "feasible"):
            w = optimum[typ]
            ids = w["hit_claims"]
            hits = {claims[s] for s in ids}
            need(len(hits) == len(ids), "hit count")
            fixed, sums, by_tier = cold.maxima(service, hits)
            need(
                sums["new_max_us"] == w["group_max_sum_us"],
                "solver/four-worker maximum",
            )
            hitjobs = {
                k: {**j, "read": 0 if k in hits else j["read"]}
                for k, j in service[0].items()
            }
            times = []
            for scale in SCALES:
                got = cold.c295.simulate(
                    (hitjobs, *service[1:]), None, scale, cold.ARENA
                )["decode_us"]
                need(
                    math.isclose(
                        got, fixed + scale * sums["new_max_us"], abs_tol=1e-4, rel_tol=0
                    ),
                    "C295 witness simulation",
                )
                times.append(got)
            if mode == "control":
                compare = previous[typ]
                need(
                    list(map(list, optimum["chosen"])) == previous["chosen"]
                    and ids == compare["hit_claims"]
                    and w["group_max_sum_us"] == compare["group_max_sum_us"]
                    and all(
                        math.isclose(t, h["decode_us"], abs_tol=1e-4, rel_tol=0)
                        for t, h in zip(times, compare["scales"], strict=True)
                    ),
                    "saved K=378 control",
                )
            else:
                if typ == "optimistic":
                    need(
                        all(
                            x <= y + 1e-4
                            for x, y in zip(times, latest[typ], strict=True)
                        ),
                        "relaxed optimum increased",
                    )
                counts = w["hit_counts"]["decode"]
                n_primary = {t: subtotal[t]["jobs"] for t in TIERS}
                report = {
                    k: w[k]
                    for k in (
                        "peak_slots",
                        "peak_bytes",
                        "occupied_at_I",
                        "fits",
                        "final_slots",
                        "hit_counts",
                        "materializations",
                        "materialized_bytes_by_origin_tier",
                        "RAM_to_staging_bytes",
                        "dropped_repeat_intervals",
                        "group_max_sum_us",
                    )
                }
                report.update(
                    chosen_count=len(optimum["chosen"]),
                    selection_sha256=sanitized_hash(optimum["chosen"]),
                    hit_claims_sha256=sanitized_hash(ids),
                    fixed_us=fixed,
                    decode_us=times,
                    slack_us=[cold.BUDGET_US - t for t in times],
                    steps_per_s=[32e6 / t for t in times],
                    time_by_tier_group_max_us={
                        t: by_tier[t]["new_max_us"] for t in TIERS
                    },
                    primary_set_payload_removed_cpu_bytes=n_primary["CPU"] * PAYLOAD,
                    primary_set_payload_remaining_cuda_bytes=n_primary["CUDA0"]
                    * PAYLOAD,
                    original_reads_payload_bytes={
                        t: n_primary[t] * PAYLOAD for t in TIERS
                    },
                    primary_read_payload_avoided_bytes={
                        t: counts[t] * PAYLOAD for t in TIERS
                    },
                    primary_read_payload_remaining_bytes={
                        t: (n_primary[t] - counts[t]) * PAYLOAD for t in TIERS
                    },
                    L2_hit_payload_to_consumer_bytes={
                        t: counts[t] * PAYLOAD for t in TIERS
                    },
                    max_admissible_service_scale=(cold.BUDGET_US - fixed)
                    / sums["new_max_us"],
                )
                out["cases"].setdefault(mode, {})[typ] = report
            latest[typ] = times
        need(
            optimum["feasible"]["fits"]
            and optimum["feasible"]["peak_slots"] <= CAP
            and optimum["optimistic"]["group_max_sum_us"]
            <= optimum["feasible"]["group_max_sum_us"],
            "capacity relaxation",
        )
    return out


def run(repo, raw):
    unit = repo / "research/qualification-retake"
    sys.path.insert(0, str(unit))
    from l2_decode_entry import screen as base

    prior = json.loads(pinned(unit / "l2_decode_entry/evidence/receipt.json", PRIOR))
    for label, digest in prior["sources_sha256"].items():
        pinned(unit / label, digest)
    pinned(Path(base.cold.c295.__file__), prior["C295_program_sha256"])
    need(prior["status"] == "PASS_CONDITIONAL_DECODE_ENTRY_BOUNDS", "prior control")
    scenario = json.loads(
        pinned(
            repo
            / "results/c295-activation-byte-optimistic-scenario-20261006/scenario.json",
            prior["C295_scenario_sha256"],
        )
    )
    results = {}
    for case in ("nominal153", "code153"):
        for h in scenario["cases"][case]:
            name = h["run"]
            results[name] = arm(
                base, raw, name, prior["arms"][name], h["service_sensitivity"]
            )
    need(len(results) == 4 and set(results) == set(prior["arms"]), "four closed arms")
    decisions = {}
    for case in ("nominal153", "code153"):
        names = [f"c294-{case}-{i}-on" for i in (2, 3)]
        decisions[case] = {}
        for mode in ("free_cpu_set", "free_cpu_set_and_residual"):
            decisions[case][mode] = []
            for i in range(3):
                cells = [results[n]["cases"][mode] for n in names]
                status = (
                    "NO_GO"
                    if any(c["optimistic"]["slack_us"][i] < 0 for c in cells)
                    else "GO_CAUSAL_FIXTURE_ONLY"
                    if all(c["feasible"]["slack_us"][i] >= 0 for c in cells)
                    else "INCONCLUSIVE"
                )
                decisions[case][mode].append(status)
    return {
        "status": "REPRODUCED_JOINT_C294_C295_CONDITIONAL_BOUNDS",
        "prior_sha256": PRIOR,
        "arms": results,
        "decisions": decisions,
        "scales": SCALES,
        "capacity": CAP,
        "expert_bytes": PAYLOAD,
        "budget_us": base.cold.BUDGET_US,
        "protocol_sha256": PROTOCOL,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ("repo", "raw-dir", "new-output-dir"):
        parser.add_argument("--" + n, type=Path, required=True)
    a = parser.parse_args()
    out = a.new_output_dir.resolve()
    need(not out.is_relative_to(a.raw_dir.resolve()), "output overlaps trace")
    hard = resource.getrlimit(resource.RLIMIT_AS)[1]
    resource.setrlimit(
        resource.RLIMIT_AS, (min(hard, 768 << 20) if hard >= 0 else 768 << 20, hard)
    )

    def timeout(*_):
        raise TimeoutError("120s budget")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    os.umask(0o077)
    out.mkdir(exist_ok=False)
    try:
        pinned(Path(__file__).with_name("protocol.md"), PROTOCOL)
        receipt = run(a.repo.resolve(), a.raw_dir.resolve())
    except Exception as err:
        receipt = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(err, FileNotFoundError)
            else "FAIL_PRESERVED",
            "reason": f"{type(err).__name__}: {err}",
        }
    buf = (
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    need(len(buf) <= 2 << 20, "receipt size")
    with (out / ".pending").open("xb") as f:
        f.write(buf)
        f.flush()
        os.fsync(f.fileno())
    os.link(out / ".pending", out / "receipt.json")
    (out / ".pending").unlink()
    print(receipt["status"])
    return int("arms" not in receipt)


if __name__ == "__main__":
    raise SystemExit(main())
