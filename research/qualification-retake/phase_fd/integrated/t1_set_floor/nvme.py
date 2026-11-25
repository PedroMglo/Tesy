"""Conditional SET floor at two individually observed, authenticated NVMe READ prices."""

import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("local_set_service_floor", HERE / "screen.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
src, need = base.src, base.need
METHOD = "eab6aa8b8be715773f7ac91e2534194b2d45e886a8327b97d2cb6c3323c7fe54"
SET_CODE = "77b7160b6bded99525bee58040911f266329d1505edd564634702d062febe4a8"
SET_REF = "3402d411f6baf85cfe82067bf106730776939b4822317e11dee40b3a654d0029"
ARCHIVE = "f8ebc57b45bebf112e69e9702be8dcf63e50fc469bc174f80256fa1ab4035970"
PHYSICAL = "ff1a6efa015ebb48d0660c77c3afc66bac86d35d82c5cda9cde72062b365f50e"


def match_plan(local, original):
    need(len(local) == len(original), "number of waves")
    seen = set()
    for new, old in zip(local, original, strict=True):
        need(
            new["site"] == old["site"] and len(new["experts"]) == len(old["experts"]),
            "wave identity/order/width",
        )
        for n, o in zip(new["experts"], old["experts"], strict=True):
            for field in ("expert", "slot", "generation", "components", "ranges"):
                need(n[field] == o[field], f"cross-plan mismatch: {field}")
            need(
                len(n["components"]) == len(n["ranges"]) == 3
                and sorted(n["components"]) == [0, 1, 2],
                "complete components",
            )
            k = new["site"][2], n["expert"]
            need(k not in seen, "duplicate first lookup")
            seen.add(k)
    return seen


def price_log(plan, logs):
    need(len(plan) == len(logs), "log wave count")
    prices = {}
    worker_ns = total_floor = aligned = payload = 0
    for wave, log in zip(plan, logs, strict=True):
        ordered = wave["experts"]
        need(
            wave["site"] == log["site"]
            and len(ordered) == len(log["jobs"]) > 0
            and log["order_indices"] == list(range(len(ordered))),
            "physical release/FIFO",
        )
        chains = []
        workers = set()
        for job, real in zip(ordered, log["jobs"], strict=True):
            need(
                real["expert"] == job["expert"] and real["role"] == "demand",
                "physical expert order",
            )
            spans = real["read_spans_ns"]
            need(
                len(spans) == len(job["components"]) == len(job["ranges"]) == 3
                and all(
                    0 <= log["release_cost_ns"] <= a < b <= real["finish_ns"] <= log["drain_ns"]
                    for a, b in spans
                )
                and spans[0][1] <= spans[1][0]
                and spans[1][1] <= spans[2][0],
                "three physical serial READs",
            )
            components = [b - a for a, b in spans]
            cost = sum(components)
            workers.add(real["worker_id"])
            key = wave["site"][2], real["expert"]
            need(key not in prices, "duplicate priced key")
            prices[key] = cost
            chains.append(cost)
            aligned += sum(s[3] for s in job["ranges"])
            payload += sum(s[1] for s in job["ranges"])
        need(len(workers) <= 4, "worker count")
        floor = max(max(chains), sum(chains) // 4)
        need(
            sum(chains) == log["read_worker_ns"]
            and floor == log["floor_ns"]
            and max(chains) == log["longest_job_ns"],
            "per-wave recorded durations",
        )
        worker_ns += sum(chains)
        total_floor += floor
    return prices, dict(
        read_worker_ns=worker_ns,
        floor_ns=total_floor,
        aligned_bytes=aligned,
        logical_bytes=payload,
        components=3 * len(prices),
        groups_completed=len(logs),
    )


def witness(groups, eligible, volume, budgets, fixed, local_control):
    dp, back = base.solve(groups, eligible, 1, 1)
    output = []
    for control in local_control:
        cap = control["capacity"]
        q = min(cap, len(dp) - 1)
        chosen = back(q)
        chosen.update(sorted(eligible - chosen, key=lambda k: (k not in volume, k))[: cap - q])
        n = sum(base.bounds(g, chosen, 1, 1) for g in groups)
        need(
            n == dp[q] and len(chosen) == min(cap, len(eligible)) and chosen <= eligible,
            "external-price witness",
        )
        elapsed = fixed + n // 4
        nbytes = len(volume - chosen) * src.possible.warm.PAYLOAD
        best_volume = (len(volume) - min(cap, len(volume & eligible))) * src.possible.warm.PAYLOAD
        decisions = {
            den: (
                "NO_GO_AT_THIS_MEASURED_READ_PRICE"
                if elapsed > 10**10 or best_volume > budget
                else "HEADROOM_ONLY_CAUSAL_POLICY_REQUIRED"
                if nbytes <= budget
                else "INCONCLUSIVE_VOLUME_TRADEOFF"
            )
            for den, budget in budgets.items()
        }
        output.append(
            {
                "capacity": cap,
                "eligible_jobs_selected": q,
                "selected_keys": len(chosen),
                "selection_sha256": src.audit.digest(sorted(chosen)),
                "selected_by_tier": src.audit.per_tier(chosen),
                "service_numerator": n,
                "service_denominator": 4,
                "first_floor_ns": elapsed,
                "remaining_time_budget_ns": 10**10 - elapsed,
                "difference_from_local_read_price_ns": elapsed - control["first_floor_ns"],
                "selected_prefill_volume_keys": len(chosen & volume),
                "prefill_volume_floor_bytes": nbytes,
                "best_possible_volume_floor_bytes": best_volume,
                "decisions": decisions,
            }
        )
    return output


def run(a):
    need(
        base.sha(HERE / "nvme-protocol.md") == METHOD and base.sha(HERE / "screen.py") == SET_CODE,
        "protocol/code",
    )
    previous = src.pinned(HERE / "evidence/receipt.json", SET_REF)
    raw_arms = src.pinned(base.INT / "cold_read_fixture/physical/receipt.json", PHYSICAL)
    manifest = src.pinned(a.nvme_part / "manifest.json", ARCHIVE)
    files = manifest["files"]
    need(manifest["part"] == "part-38" and len(files) == 26, "physical archive")

    def file(name, digest=None):
        item = files[name]
        path = a.nvme_part / name
        need(
            path.is_file()
            and not path.is_symlink()
            and item["bytes"] == path.stat().st_size
            and item["sha256"] == base.sha(path)
            and (digest is None or item["sha256"] == digest),
            "archive " + name,
        )
        return path

    def document(name, digest=None):
        return json.loads(file(name, digest).read_bytes())

    prep = src.pinned(a.prepared_dir / "receipt.json", base.PREP)
    ref = src.pinned(a.score_dir / "receipt.json", base.SCORE)
    need(
        prep["status"] == "PASS_PREFIX_ONLY"
        and prep["selection_sha256"] == base.sha(a.prepared_dir / "selection.json")
        and ref["status"] == "PASS_SINGLE_SESSION_DIAGNOSTIC"
        and ref["source_sha256"] == base.sha(base.INT / "t1_local/source.py")
        and previous["status"] == "PASS_CONDITIONAL_SET_SERVICE_FLOOR"
        and previous["program_sha256"] == SET_CODE,
        "previous local controls",
    )
    inp = src.load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
    start = int(inp.client["request_started_monotonic"] * 10**9)
    first = start + int(inp.client["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    local, _ = src.admit.t2.planner.assemble(inp.rows, inp.meta, start, first)
    observed, conserve = base.extract(inp.rows, local, inp.meta, start, first)
    need(
        conserve == previous["conservation"] and inp.journal == previous["journal_sha256"],
        "local SET conservation",
    )
    digest = raw_arms["arms"][0]["plan_sha256"]
    other = document("tesy-cold-first-plan-20261125-r0" + str(a.copy) + "/plan.json", digest)
    identities = match_plan(local, other["groups"])
    need(len(identities) == 875 and len(local) == 441, "identical first jobs")
    fixed = previous["first_fixed_ns"]
    volume = src.admit.t2.eligible_sets(inp.rows)["victims"]
    eligible = set(map(tuple, inp.available["evicted_ready"]))
    out = {}
    first_hashes = None
    for i, arm in enumerate(raw_arms["arms"], 1):
        anchor = f"pfj-first-nvme-20261125-r0{i}/"
        raw = document(anchor + "receipt.json", arm["receipt_sha256"])
        need(
            raw["status"] == arm["status"] == "PASS_FIRST_DEMAND_NVME_TRAVERSAL"
            and raw["direct_flag"]
            and raw["plan_sha256"] == digest
            and raw["forward_passes"] == 0,
            "physical arm",
        )
        hashes = document(anchor + "payloads.json", arm["payload_manifest_sha256"])
        need(
            hashes
            and len(hashes) == 2625
            and all(re.fullmatch("[0-9a-f]{64}", v) for v in hashes)
            and (first_hashes is None or hashes == first_hashes),
            "component payload agreement",
        )
        first_hashes = hashes
        records = [
            json.loads(line)
            for line in file(anchor + "raw/groups.jsonl", arm["groups_sha256"])
            .read_bytes()
            .splitlines()
        ]
        prices, stats = price_log(local, records)
        need(
            prices.keys() == identities
            and all(raw[n] == arm[n] == count for n, count in stats.items()),
            "conservation across process receipts",
        )
        priced = [[j._replace(read=prices[j.key]) if j.first else j for j in g] for g in observed]
        out[str(i)] = dict(
            physical_receipt_sha256=arm["receipt_sha256"],
            groups_sha256=arm["groups_sha256"],
            payload_manifest_sha256=arm["payload_manifest_sha256"],
            controls=stats,
            rows=witness(
                priced,
                eligible,
                volume,
                previous["volume_budget_bytes"],
                fixed,
                previous["cases"]["1/1"],
            ),
        )
    return dict(
        status="PASS_TWO_INDEPENDENT_CONDITIONAL_READ_PRICES",
        new_forwards=0,
        capture_status="FAIL_PRESERVED",
        clock="LOCAL_T2_FIXED_AND_SETS_PLUS_EXTERNAL_DURATIONS_ONLY",
        physical_arms=out,
        local_set_receipt_sha256=SET_REF,
        archive_manifest_sha256=ARCHIVE,
        archive_physical_compact_sha256=PHYSICAL,
        plan_sha256=digest,
        local_journal_sha256=inp.journal,
        local_fixed_ns=fixed,
        volume_budget_bytes=previous["volume_budget_bytes"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "part",
        "nvme-part",
        "model",
        "inventory",
        "prepared-dir",
        "score-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--copy", choices=(1, 2), type=int, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(protocol_sha256=METHOD, program_sha256=base.sha(Path(__file__)))
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
