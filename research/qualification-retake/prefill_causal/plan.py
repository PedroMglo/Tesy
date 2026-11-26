"""Replay causal placement from empty C294 pools through the 153-token increment."""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from itertools import groupby
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path[:0] = [str(UNIT), str(UNIT / "warm_policy")]
from warm_policy.evaluate import case_inputs, family_inputs, read_pinned  # noqa: E402
from warm_policy_controls.replay import EXPERT_BYTES  # noqa: E402
from warm_route_reference.verify import PROMPT  # noqa: E402
from warm_routes40.witness import read, require  # noqa: E402

FAMILY_SHA = "bd69474a52d58cf5e96e88099c20094d3fe98bb285fb14f8d82bcc516273e01a"
TIERS = ("CPU", "CUDA0")
RULES = ("votes", "lru")
C294_SOURCE = {
    "revision": "237e3b8789650fd68b97641c5b8e259d198ed3b1",
    "tree": "149078c009a40b2c69ee126cdb84091fe3e95606",
    "src/llama-graph.cpp": "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288",
    "src/llama-moe-stream.cpp": "270ede951c3911c8acbd878600f7bab3692215b820d5853d67071b790297f9fc",
}


def waves(rows):
    """First-touch slices from plan_waves_locked, retaining the row/rank order of each slice."""
    require(1 <= len(rows) <= 32, "ub32 routed width")
    for ids in rows:
        require(
            len(ids) == len(set(ids)) == 4 and all(type(x) is int and 0 <= x < 128 for x in ids),
            "invalid original top-4",
        )
    ordered = [expert for row in rows for expert in row]
    n_touch_max = min(128, len(ordered))
    if n_touch_max <= 40:
        return [ordered]
    # The graph schedules even trailing all-masked waves. They cast no votes.
    buckets = [[] for _ in range((n_touch_max + 17) // 18)]
    index = {expert: i // 18 for i, expert in enumerate(dict.fromkeys(ordered))}
    for expert in ordered:
        buckets[index[expert]].append(expert)
    return buckets


class Pool:
    """A layer-local cache. Both policies select victims before applying any vote or touch."""

    def __init__(self, policy, capacity=40):
        require(policy in RULES and 0 < capacity <= 128, "cache policy or capacity")
        self.policy = policy
        self.capacity = capacity
        self.resident = set()
        self.votes = [0] * 128
        self.last = [0] * 128
        self.clock = 0

    def serve(self, ranks):
        pinned = set(ranks)
        require(len(pinned) <= self.capacity, "simultaneous wave exceeds capacity")
        incoming = pinned - self.resident
        evictions = max(0, len(self.resident) + len(incoming) - self.capacity)
        eligible = self.resident - pinned
        if evictions:
            if self.policy == "votes":
                victims = sorted(eligible, key=lambda e: (self.votes[e], self.last[e], e))
            else:
                victims = sorted(eligible, key=lambda e: (self.last[e], e))
            self.resident.difference_update(victims[:evictions])
        self.resident.update(incoming)
        require(len(self.resident) <= self.capacity and pinned <= self.resident, "lost pin")
        for expert in ranks:
            self.clock += 1
            self.votes[expert] += 1
            self.last[expert] = self.clock
        return Counter(
            misses=len(incoming),
            hits=len(pinned) - len(incoming),
            evictions=evictions,
            distinct_demands=len(pinned),
            rank_uses=len(ranks),
            waves=int(bool(ranks)),
            parking_only_waves=int(not ranks),
        )


def check_geometry(graphs, case):
    sizes = [256] * 7 + [PROMPT[case] - 153 - 7 * 256, 153] + [1] * 32
    start = 0
    expected = []
    for call, size in enumerate(sizes, 1):
        for ub, offset in enumerate(range(0, size, 32), 1):
            expected.append(
                (call, ub, tuple(range(start + offset, start + min(size, offset + 32))))
            )
        start += size
    require(graphs == expected, "prefix calls, ub32, increment or decode positions differ")


def project_i(pools, target):
    """Minimum loads to restore membership without a physical slot-order constraint."""
    require(len(pools) == len(target) == 36, "I layers")
    result = {tier: Counter(loads=0, excess_identities=0) for tier in TIERS}
    for layer, (pool, wanted) in enumerate(zip(pools, target, strict=True)):
        require(
            len(wanted) <= pool.capacity and all(type(e) is int and 0 <= e < 128 for e in wanted),
            "invalid restore target",
        )
        tier = TIERS[int(layer >= 25)]
        result[tier]["loads"] += len(wanted - pool.resident)
        result[tier]["excess_identities"] += len(pool.resident - wanted)
    for stats in result.values():
        stats["logical_load_bytes"] = stats["loads"] * EXPERT_BYTES
    return result


def simulate(rows, policy, target):
    pools = [Pool(policy) for _ in range(36)]
    phases = {phase: {tier: Counter() for tier in TIERS} for phase in ("prefix", "increment")}
    p_signature = None
    for (call, _, layer), entries in groupby(rows, key=lambda row: row[:3]):
        if call > 9:
            break
        if call == 9 and p_signature is None:
            p_signature = membership_digest(pools)
        ranks = [ids for _, _, _, _, ids in entries]
        stats = phases["prefix" if call < 9 else "increment"][TIERS[int(layer >= 25)]]
        for uses in waves(ranks):
            stats.update(pools[layer].serve(uses))
    require(p_signature is not None, "no P or increment")
    for phase in phases.values():
        for stats in phase.values():
            require(stats["hits"] + stats["misses"] == stats["distinct_demands"], "demand count")
            stats["logical_load_bytes"] = stats["misses"] * EXPERT_BYTES
    totals = [phases[x][tier] for x in phases for tier in TIERS]
    require(
        sum(s["rank_uses"] for s in totals) == sum(pool.clock for pool in pools)
        and sum(s["misses"] - s["evictions"] for s in totals)
        == sum(len(p.resident) for p in pools),
        "vote or resident conservation",
    )
    return {
        "phases": phases,
        "restore_I_identity_floor": project_i(pools, target),
        "P_membership_sha256": p_signature,
        "I_membership_sha256": membership_digest(pools),
    }


def membership_digest(pools):
    data = json.dumps([sorted(pool.resident) for pool in pools], separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def totals(policy):
    prefix, increment = (
        sum(stats["misses"] for stats in policy["phases"][phase].values())
        for phase in ("prefix", "increment")
    )
    restore = sum(stats["loads"] for stats in policy["restore_I_identity_floor"].values())
    return {
        "prefix": prefix,
        "increment": increment,
        "restored_total": prefix + increment + restore,
    }


def compare(candidate, control):
    delta = {k: candidate[k] - control[k] for k in candidate}
    tests = {
        "increment_at_least_10pct_lower": candidate["increment"] * 10 <= 9 * control["increment"],
        "prefix_no_more": delta["prefix"] <= 0,
        "restored_total_no_more": delta["restored_total"] <= 0,
    }
    return {
        "delta_loads": delta,
        "delta_payload_bytes": {k: d * EXPERT_BYTES for k, d in delta.items()},
        "tests": tests,
        "pass": all(tests.values()),
    }


def git(checkout, *args):
    proc = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True)
    require(proc.returncode == 0, "git identity unavailable: " + checkout.name)
    return proc.stdout.strip()


def check_source(historical_results):
    checkout = historical_results.parent / "backends/c294-service-window"
    require(
        git(checkout, "rev-parse", "HEAD") == C294_SOURCE["revision"]
        and git(checkout, "rev-parse", "HEAD^{tree}") == C294_SOURCE["tree"],
        "C294 pinned commit or tree differs",
    )
    for name, digest in C294_SOURCE.items():
        if name.startswith("src/"):
            read_pinned(checkout / name, digest)


def evaluate(family, historical_results):
    from prefill_causal.r0 import case_control

    check_source(historical_results)
    arms = family_inputs(family, FAMILY_SHA)
    cases = {}
    for case in PROMPT:
        _, fingerprint = case_inputs(family, case, arms)
        pair = [arm for arm in arms if arm["case"] == case]
        chosen = next(a for a in pair if a["mode"] == "OFF")
        wrt = read_pinned(
            family / chosen["native_dir"] / "routed-witness.bin",
            chosen["native_sha256"]["routed-witness.bin"],
        )
        graphs, rows = read(wrt)
        check_geometry(graphs, case)
        controls, target = case_control(historical_results, case)
        snapshot = json.loads(
            read_pinned(
                family / chosen["native_dir"] / "boundary-i.json",
                chosen["native_sha256"]["boundary-i.json"],
            )
        )
        require(
            target == [{e for e, _, s, _ in pool if s == 2} for pool in snapshot["slot_vector"]],
            "historical I members disagree with WRT family I",
        )
        policies = {rule: simulate(rows, rule, target) for rule in RULES}
        for policy in policies.values():
            expected = {
                "prefix": ((PROMPT[case] - 153) * 35 + 8) * 4,
                "increment": (153 * 35 + 1) * 4,
            }
            for phase, total in expected.items():
                require(
                    sum(s["rank_uses"] for s in policy["phases"][phase].values()) == total,
                    "vote coverage",
                )
        candidate = totals(policies["votes"])
        contrasts = {"lru": compare(candidate, totals(policies["lru"]))}
        for name, control in controls.items():
            require(control["boundary_slot_vector_sha256"] == fingerprint, "historical I differs")
            reference = {
                phase: sum(control["tiers"][tier][phase + "_loads"] for tier in TIERS)
                for phase in ("prefix", "increment")
            }
            reference["restored_total"] = reference["prefix"] + reference["increment"]
            contrasts[name] = compare(candidate, reference)
        require(len(controls) == 2, "incomplete R0 comparison")
        cases[case] = {
            "source_pair": {
                a["mode"]: {
                    "run_id": a["run_id"],
                    "P": a["P_sha256"],
                    "I": a["I_sha256"],
                    "F": a["F_sha256"],
                    "inputs": a["native_sha256"],
                }
                for a in pair
            },
            "simulated": policies,
            "historical": controls,
            "contrasts": contrasts,
            "pass": all(c["pass"] for c in contrasts.values()),
        }
    return {
        "status": "GO_FIXTURE_ONLY" if all(c["pass"] for c in cases.values()) else "NO_GO",
        "scope": "TRACE_DERIVED_C294_PREFIX_AND_INCREMENT_LOGICAL_PAYLOAD",
        "family_sha256": FAMILY_SHA,
        "C294_wave_source": C294_SOURCE,
        "expert_bytes": EXPERT_BYTES,
        "relaxation": "Only demanding wave pinned; parking and transfers between slots are free; "
        "I repair covers identity membership only.",
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--historical-results", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    identity = {
        "commit": git(HERE, "rev-parse", "HEAD"),
        "tree": git(HERE, "rev-parse", "HEAD^{tree}"),
        "clean_before_output": not git(
            HERE, "status", "--porcelain=v1", "--untracked-files=normal"
        ),
    }
    args.new_output_dir.mkdir(mode=0o700)
    try:
        require(identity["clean_before_output"], "measurement worktree must be clean")
        receipt = evaluate(args.family, args.historical_results)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as e:
        receipt = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(e, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(e),
        }
    receipt["measurement_checkout"] = identity
    receipt["code_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__).resolve(), HERE / "r0.py", HERE / "protocol.md")
    }
    tmp = args.new_output_dir / ".pending"
    with tmp.open("x") as f:
        f.write(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(args.new_output_dir / "receipt.json")
    print(receipt["status"])
    return 0 if "cases" in receipt else 1


if __name__ == "__main__":
    sys.exit(main())
