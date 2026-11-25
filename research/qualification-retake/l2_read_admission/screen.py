"""Replay inclusive encoded RAM caching at worker claim/publication in C294."""

import argparse
import hashlib
import json
import resource
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cache_boundary as boundary  # noqa: E402
from l2_read_admission.oracle import bounds  # noqa: E402
from warm_residency import replay as warm  # noqa: E402

require = boundary.require
EXPERT = warm.EXPERT
MAX_SCORE = 65535
MANAGER_SHA = "270ede951c3911c8acbd878600f7bab3692215b820d5853d67071b790297f9fc"
TIERS = ["CPU"] * 25 + ["CUDA0"] * 11
PHASES = ("increment", "decode")


def service_arm(raw, name):
    # Validates P4 reservations/promotions, all P5/6..9/10 transitions, I and F.
    _, proof = boundary.audit_arm(raw, name)
    directory = raw / (name + ".native")
    hashes = proof["source_sha256"]
    initial = json.loads(warm.checked(directory / "initial.json", hashes["initial.json"]))
    layers = sorted(initial["layers"], key=lambda layer: layer["layer"])
    require([r["native_cache_buffer"] for r in layers] == TIERS, "placement")
    require(all(r["logical_bytes_per_load"] == EXPERT for r in layers), "expert size")
    data = warm.checked(directory / "events.tsv", hashes["events.tsv"])
    jobs = {p: [] for p in PHASES}
    claimed = {}
    seen_generations = set()
    readers = Counter()
    cut_i = False
    peak_workers = 0
    for seq, line in enumerate(data.splitlines()[1:]):
        kind, _, call, _, layer, expert, slot, gen, component, size, _ = map(int, line.split())
        if (kind, call) == (16, 0):
            require(not cut_i and not claimed, "I cut while a job is in flight")
            cut_i = True
        if kind not in (5, 6, 10):
            continue
        phase = "decode" if cut_i else "increment"
        require((call == 0) == (phase == "increment"), "event straddles I")
        key = (layer, expert)
        generation = (layer, slot, gen)
        if kind == 5:
            require(generation not in seen_generations and key not in claimed, "duplicate service")
            seen_generations.add(generation)
            claimed[key] = (seq, generation, call)
            peak_workers = max(peak_workers, len(claimed))
        else:
            require(key in claimed and claimed[key][1:] == (generation, call), "unmatched service")
            if kind == 6:
                require(size == EXPERT // 3 and 0 <= component < 3, "wrong logical read size")
                readers[phase, TIERS[layer]] += 1
            else:
                begin, _, _ = claimed.pop(key)
                jobs[phase].append((begin, seq, key))
    require(cut_i and not claimed and 1 <= peak_workers <= 4, "unfinished service or worker limit")
    for phase, label in zip(PHASES, ("prefill", "decode"), strict=True):
        jobs[phase].sort()
        cnt = proof["counts"]
        n = len(jobs[phase])
        require(n == cnt[label + "_new"] == cnt[label + "_publications"], "primary conservation")
        for tier in ("CPU", "CUDA0"):
            require(
                readers[phase, tier] == 3 * sum(TIERS[k[0]] == tier for _, _, k in jobs[phase]),
                "primary component count",
            )
    return jobs, {
        "source_sha256": hashes,
        "primary_I_sha256": proof["boundary_slot_vector_sha256"],
        "peak_claims": peak_workers,
    }


def replay(jobs, capacity, policy):
    require(policy in ("always_lru", "frequency_gate") and capacity > 0, "invalid policy")
    residents = {}  # last successful hit at lookup or insertion at publication
    counts = Counter()
    first_use_pending = {}
    reused_admissions = Counter()
    phases = {}
    for phase in PHASES:
        stats = {
            tier: Counter(lookups=0, hits=0, nvme_reads=0, admissions=0, bypasses=0)
            for tier in ("CPU", "CUDA0")
        }
        events = sorted(
            (seq, lookup, key)
            for start, end, key in jobs[phase]
            for seq, lookup in ((start, True), (end, False))
        )
        active = {}
        for seq, lookup, key in events:
            c = stats[TIERS[key[0]]]
            if lookup:
                require(key not in active, "simultaneous primary generations for one expert")
                old_score = counts[key]
                counts[key] = min(MAX_SCORE, old_score + 1)
                hit = key in residents
                active[key] = (hit, old_score)
                c["lookups"] += 1
                if hit:
                    c["hits"] += 1
                    if key in first_use_pending:
                        reused_admissions[first_use_pending.pop(key)] += 1
                    residents[key] = seq
                else:
                    c["nvme_reads"] += 1
                continue
            require(key in active, "publication has no claim")
            hit, old_score = active.pop(key)
            if hit:
                continue  # private worker staging protects an in-flight hit after L2 eviction
            require(key not in residents, "late duplicate admission")
            if len(residents) == capacity:
                if policy == "always_lru":
                    victim = min(residents, key=lambda k: (residents[k], k))
                else:
                    victim = min(residents, key=lambda k: (counts[k], residents[k], k))
                    if old_score <= counts[victim]:
                        c["bypasses"] += 1
                        continue
                del residents[victim]
                first_use_pending.pop(victim, None)
            residents[key] = seq
            first_use_pending[key] = (phase, TIERS[key[0]])
            c["admissions"] += 1
        require(not active and len(residents) <= capacity, "undrained phase or pool overflow")
        for tier, c in stats.items():
            require(
                c["lookups"] == c["hits"] + c["nvme_reads"]
                and c["nvme_reads"] == c["admissions"] + c["bypasses"],
                "L2 conservation",
            )
            c["logical_read_bytes"] = EXPERT * c["nvme_reads"]
            c["host_copy_on_admission_bytes"] = EXPERT * c["admissions"]
            c["hit_to_private_staging_bytes"] = EXPERT * c["hits"]
            c["primary_tensor_set_payload_bytes"] = EXPERT * c["lookups"]
            c["primary_h2d_payload_bytes"] = EXPERT * c["lookups"] if tier == "CUDA0" else 0
        total = Counter()
        for c in stats.values():
            total.update(c)
        phases[phase] = {"tiers": stats, "total": total, "resident_at_end": len(residents)}
    for phase in PHASES:
        totals = phases[phase]["total"]
        for tier, c in phases[phase]["tiers"].items():
            reused = reused_admissions[phase, tier]
            c["admissions_reused_by_F"] = reused
            c["admissions_unused_by_F"] = c["admissions"] - reused
            totals["admissions_reused_by_F"] += reused
            totals["admissions_unused_by_F"] += c["admissions"] - reused
    return phases


def grade(causal, lru):
    c = causal["decode"]["total"]
    control = lru["decode"]["total"]
    total_reads = sum(causal[p]["total"]["nvme_reads"] for p in PHASES)
    lru_reads = sum(lru[p]["total"]["nvme_reads"] for p in PHASES)
    return {
        "decode_20pct": 5 * c["hits"] >= c["lookups"],
        "decode_beats_lru": c["hits"] > control["hits"],
        "window_no_additional_reads": total_reads <= lru_reads,
        "window_reads": total_reads,
        "window_lru_reads": lru_reads,
    }


def analyse(raw, backend):
    manager = backend / "src/llama-moe-stream.cpp"
    warm.checked(manager, MANAGER_SHA)
    peaks = {
        p: json.loads(warm.checked(HERE.parent / p, sha))["maxima"]["cgroup_peak_bytes"]
        for p, sha in warm.MEASURED.items()
    }
    headroom = warm.STOP - max(peaks.values())
    caps = {"3GiB": 3 * 2**30 // EXPERT, "E20_payload_only": headroom // EXPERT}
    require(tuple(caps.values()) == (243, 378), "changed capacity calculation")
    arms = {}
    decoded = {}
    for name in boundary.NAMES:
        jobs, identity = service_arm(raw, name)
        scenarios = {}
        for cap_name, capacity in caps.items():
            causal = replay(jobs, capacity, "frequency_gate")
            lru = replay(jobs, capacity, "always_lru")
            oracle = bounds(jobs["increment"], jobs["decode"], capacity)
            for policy in (causal, lru):
                require(
                    sum(policy[p]["total"]["hits"] for p in PHASES) <= oracle["joint_hits"]
                    and policy["decode"]["total"]["hits"] <= oracle["decode_only_hits"],
                    "causal replay exceeds offline bound",
                )
            scenarios[cap_name] = {
                "capacity": capacity,
                "offline": oracle,
                "frequency_gate": causal,
                "always_lru": lru,
                "grade": grade(causal, lru),
            }
        arms[name] = {**identity, "scenarios": scenarios}
    for cap_name in caps:
        # Both repeats of both supplied cases must satisfy all three signs.
        results = [v["scenarios"][cap_name] for v in arms.values()]
        candidate = all(
            all(
                x["grade"][k]
                for k in ("decode_20pct", "decode_beats_lru", "window_no_additional_reads")
            )
            for x in results
        )
        possible = all(
            5 * x["offline"]["decode_only_hits"] >= x["offline"]["decode_reads"] for x in results
        )
        decoded[cap_name] = {
            "candidate": "GO_COST_FIXTURE_ONLY" if candidate else "NO_GO_POLICY",
            "offline_joint_decode_gate_possible": possible,
        }
    return {
        "status": "TRACE_DERIVED_FIXED_PRIMARY",
        "headroom_bytes": headroom,
        "payload_bytes_per_expert": EXPERT,
        "arms": arms,
        "decisions": decoded,
        "c294_sha256": MANAGER_SHA,
        "manifest_sha256": boundary.MANIFEST_SHA,
        "sources_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), HERE / "protocol.md", HERE / "oracle.py")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument(
        "--backend", type=Path, help="C294 source (default: C7/backends/c294-service-window)"
    )
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.new_output_dir.resolve()
    require(not out.is_relative_to(args.raw_dir.resolve()), "protect raw")
    out.mkdir(exist_ok=False)
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
    signal.alarm(120)
    try:
        def git(*cmd):
            return subprocess.check_output(["git", *cmd], cwd=HERE, text=True).strip()

        commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        require(not git("status", "--porcelain=v1", "--untracked-files=normal"), "dirty checkout")
        backend = args.backend or args.raw_dir.resolve().parents[2] / "backends/c294-service-window"
        result = analyse(args.raw_dir, backend)
        result.update(commit=commit, tree=tree, clean=True)
    except FileNotFoundError as exc:
        result = {"status": "NOT_RUN_RAW_REQUIRED", "missing": Path(exc.filename).name}
    except (ValueError, KeyError, StopIteration, OSError, TypeError) as exc:
        result = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    finally:
        signal.alarm(0)
    tmp = out / "receipt.pending"
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(out / "receipt.json")
    print(result["status"])
    return int(result["status"] != "TRACE_DERIVED_FIXED_PRIMARY")


if __name__ == "__main__":
    raise SystemExit(main())
