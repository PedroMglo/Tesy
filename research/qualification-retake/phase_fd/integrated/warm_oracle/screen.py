"""Minimum omniscient T1 occupancy for the measured cold-group floor, without a model."""

import argparse
import collections
import hashlib
import json
import sys
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
sys.path.insert(0, str(INT))
import analyse  # noqa: E402
from mandatory import lower_bound, need  # noqa: E402

METHOD = "d3062250d1968da9ff7e892a171dd2aef2b20ae0ebf1061f143d65e7ae7fafe6"
LIMITS = "47476b0d8f0435c5e4c04f56a73edbb85f81e22ef9f9ba80a92c3b19b67d5b74"
VOLUME = "a3398265b4bf33ed75f4898b346c2d9a988865cd5ca9cf98668826b52d41f700"
MANDATORY = "8f83497fe6b7d403232448b72e4f06a3d28eda1a7774ab87635fef040346f930"
PAYLOAD = 13219200
CAPS = (0, 239, 353)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path, digest):
    need(sha(path) == digest, "input mismatch: " + path.name)
    return json.loads(path.read_bytes())


def optimum(groups):
    """At exactly k warm keys return the optimal remaining (unscaled) service floor."""
    seen = set()
    ordered = []
    parents = []
    dp = [0]
    for group in groups:
        checked = []
        for key, t in group:
            need(key not in seen and type(t) is int and t > 0, "invalid or duplicate service")
            seen.add(key)
            checked.append((key, t))
        need(0 < len(checked) <= 40, "empty group or exceeds primary slots")
        ordered.append(sorted(checked, key=lambda kv: (-kv[1], kv[0])))
        lengths = [t for _, t in ordered[-1]]
        costs = [lower_bound(lengths[q:]) for q in range(len(lengths) + 1)]
        values = []
        prev = array("B")
        for k in range(len(dp) + len(lengths)):
            value, take = min(
                (dp[k - q] + costs[q], q)
                for q in range(max(0, k + 1 - len(dp)), min(k, len(lengths)) + 1)
            )
            values.append(value)
            prev.append(take)
        dp = values
        parents.append(prev)
    need(
        all(a >= b for a, b in zip(dp, dp[1:], strict=False)) and dp[-1] == 0,
        "nonmonotonic frontier",
    )

    def witness(k):
        chosen = []
        for group, prev in zip(reversed(ordered), reversed(parents), strict=True):
            q = prev[k]
            chosen.extend([key for key, _ in group[:q]])
            k -= q
        need(k == 0 and len(chosen) == len(set(chosen)), "backtrack")
        return sorted(chosen)

    return dp, witness


def jobs(plan, rows):
    reads = collections.defaultdict(list)
    for row in rows:
        if row.kind == 15:
            reads[row.layer, row.expert, row.slot, row.gen].append(row)
    groups = []
    sites = set()
    for g in plan["groups"]:
        site = tuple(g["site"])
        need(site not in sites and len(site) == 4, "duplicate wave")
        sites.add(site)
        group = []
        for job in g["experts"]:
            expert, slot, gen = (job[k] for k in ("expert", "slot", "generation"))
            parts = reads[(site[2], expert, slot, gen)]
            need(
                len(parts) == 3
                and [p.component for p in parts] == job["components"]
                and len({p.worker for p in parts}) == 1
                and all((p.call, p.tile, p.layer, p.wave) == site for p in parts)
                and all(x.ns <= y.begin for x, y in zip(parts, parts[1:], strict=False))
                and all(
                    p.ns > p.begin and [p.a, p.b] == z[2:] and p.b == p.c
                    for p, z in zip(parts, job["ranges"], strict=True)
                ),
                "recorded service chain",
            )
            group.append(((site[2], expert), sum(p.ns - p.begin for p in parts)))
        groups.append(group)
    return groups


def solve(plan_dir, plan_sha, journal):
    need(
        sha(HERE / "protocol.md") == METHOD and sha(INT / "mandatory.py") == MANDATORY,
        "method identity",
    )
    ref = read(INT / "nominal-r01/limits.json", LIMITS)
    host = read(INT / "host_cache/evidence/receipt.json", VOLUME)
    meta = read(plan_dir / "receipt.json", plan_sha)
    need(
        meta["status"] == "PASS_AUTHENTICATED_FIRST_READ_PLAN"
        and meta["source_limits_sha256"] == LIMITS
        and meta["on_sha256"] == ref["sources"]["on"] == host["on_sha256"]
        and meta["off_sha256"] == ref["sources"]["off"] == host["off_sha256"],
        "plan and scopes",
    )
    plan = read(plan_dir / "plan.json", meta["plan_sha256"])
    need(
        all(plan[k] == v for k, v in meta.items() if k not in ("plan_bytes", "plan_sha256"))
        and sha(journal)
        == meta["journal_sha256"]
        == host["journal_sha256"]
        == ref["sources"]["journal"],
        "journal and private plan",
    )
    rows, head = analyse.read_journal(journal)
    need(head["journal_sha256"] == meta["journal_sha256"], "journal closure")
    groups = jobs(plan, rows)
    front, choose = optimum(groups)
    fixed = meta["fixed_outside_callbacks_ns"]
    need(
        len(front) == 876
        and front[0] == meta["original_service_floor_ns"] == 6231568365
        and fixed == 5996895714,
        "reproduce original floor",
    )
    need(
        host["required_distinct"] == 1051
        and host["cold_fixed_primary_floor_bytes"] == 1051 * PAYLOAD,
        "fixed primary volume",
    )
    result = {}
    for a, b in ((1, 1), (4, 5)):
        times = [fixed + x * a // b for x in front]
        k = next(j for j, x in enumerate(times) if x <= 10**10)

        def temporal_at(n, bounds=times):
            selected = choose(n)
            need(len(selected) == n, "witness count")
            lost = set(selected)
            check = sum(lower_bound([t for key, t in g if key not in lost]) for g in groups)
            need(check == front[n], "witness service")
            return {
                "k": n,
                "first_floor_ns": bounds[n],
                "margin_ns": 10**10 - bounds[n],
                "warm_payload_bytes": n * PAYLOAD,
                "selected_keys_sha256": hashlib.sha256(
                    json.dumps(selected, separators=(",", ":")).encode()
                ).hexdigest(),
            }

        result[f"{a}/{b}"] = {
            "minimum": temporal_at(k),
            "one_fewer": temporal_at(k - 1) if k else None,
            "capacity": [temporal_at(n) for n in CAPS],
        }
    volumes = {}
    for name, g in host["gates"].items():
        budget = g["allowed_bytes"]
        minimum = max(0, 1051 - budget // PAYLOAD)
        need(minimum == g["minimum_warm_keys_for_compulsory_floor"], "reproduce volume")
        volumes[name] = {
            "allowed_bytes": budget,
            "minimum": minimum,
            "warm_payload_bytes": minimum * PAYLOAD,
            "capacity": [
                {
                    "k": n,
                    "prefill_floor_bytes": (1051 - n) * PAYLOAD,
                    "margin_bytes": budget - (1051 - n) * PAYLOAD,
                }
                for n in CAPS
            ],
            "necessary_for_both": {q: max(v["minimum"]["k"], minimum) for q, v in result.items()},
        }
    return {
        "status": "PASS_RELAXED_WARM_MINIMA",
        "joint_schedule": "NOT_IDENTIFIED",
        "group_count": len(groups),
        "unique_keys": len(front) - 1,
        "first_fixed_ns": fixed,
        "payload_per_key": PAYLOAD,
        "temporal": result,
        "volume": volumes,
        "additional_capacity_bytes": {
            row["capacity"]: row["additional_bytes"] for row in host["capacities"]
        },
        "source": {
            "method": METHOD,
            "code": sha(Path(__file__)),
            "analyser": sha(Path(analyse.__file__)),
            "mandatory": MANDATORY,
            "host_cache": VOLUME,
            "limits": LIMITS,
            "plan_receipt": plan_sha,
            "plan": meta["plan_sha256"],
            "journal": head["journal_sha256"],
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for opt in ("plan-dir", "journal", "new-output-dir"):
        p.add_argument("--" + opt, type=Path, required=True)
    p.add_argument("--plan-sha256", required=True)
    args = p.parse_args()
    out = args.new_output_dir
    out.mkdir(mode=0o700)
    try:
        answer = solve(args.plan_dir, args.plan_sha256, args.journal)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as ex:
        answer = {"status": "FAIL_PRESERVED", "gate": str(ex), "type": type(ex).__name__}
    (out / "receipt.json").write_text(
        json.dumps(answer, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(answer["status"])
    raise SystemExit(answer["status"] == "FAIL_PRESERVED")
