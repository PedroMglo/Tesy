"""Audit a terminal measurement in read-only mode and create a sanitized no-replace receipt."""

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import statistics
from fractions import Fraction
from pathlib import Path


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def loadj(p):
    need(not p.is_symlink() and p.is_file() and p.stat().st_size < 32 * 2**20, "bad file:" + p.name)
    return json.loads(p.read_bytes())


def loadmod(p, expected):
    need(sha(p) == expected, "changed verifier:" + p.name)
    spec = importlib.util.spec_from_file_location("audit_" + p.stem, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def spread(rows):
    return {"min": min(rows), "median": statistics.median(rows), "max": max(rows)}


def audit_pairs(rows, inner):
    at = {(a["block"], a["layout"], a["observer"]): a for a in rows}
    pairs = {}
    accepted = True
    for control in ("STAGED", "DENSE"):
        obs = {}
        for channel in ("publish_ns", "resume_ns"):
            ratio = [
                Fraction(at[b, "DIRECT", "MIN"][channel], at[b, control, "MIN"][channel])
                for b in range(1, 7)
            ]
            gain = [1 - r for r in ratio]
            passed = (
                statistics.median(gain) >= Fraction(1, 20) and sum(g > 0 for g in gain) >= 5
                if channel == "publish_ns"
                else statistics.median(gain) > 0
            )
            q = inner["comparisons"][control][channel]
            need(
                q["gains"] == list(map(float, gain))
                and q["median_gain"] == float(statistics.median(gain))
                and q["positive_pairs"] == sum(g > 0 for g in gain),
                "independent_paired_audit",
            )
            obs[channel] = {
                "gains": list(map(float, gain)),
                "positive_pairs": sum(g > 0 for g in gain),
                "spread": spread(list(map(float, gain))),
                "passes": passed,
            }
            accepted = accepted and passed
        pairs[control] = obs
    detail = True
    for layout in ("DENSE", "STAGED", "DIRECT"):
        for channel in ("publish_ns", "outer_ns"):
            xs = [
                Fraction(at[b, layout, "DETAIL"][channel], at[b, layout, "MIN"][channel])
                for b in range(1, 7)
            ]
            ok = (
                Fraction(95, 100) <= statistics.median(xs) <= Fraction(105, 100)
                and sum(Fraction(85, 100) <= x <= Fraction(115, 100) for x in xs) >= 5
            )
            original = inner["neutral"][layout][channel]
            need(
                original["passes"] == ok and original["ratios"] == list(map(float, xs)),
                "independent_neutrality_audit",
            )
            detail = detail and ok
    need(
        accepted == (inner["decision"] == "GO_NEXT_SERVICE_SCOPE")
        and detail == (inner["detail_class"] == "QUALIFIED_DETAIL"),
        "independent_decision",
    )
    return pairs


def summarize_detail(doc, review):
    t = doc["t0"]
    receipt = dict(
        (k, review[k])
        for k in [
            "read_worker_ns",
            "set_worker_ns",
            "read_union_ns",
            "set_union_ns",
            "read_or_set_union_ns",
            "last_experts",
        ]
    )
    jobs = []
    for job in review["jobs"]:
        exp = job["expert"]
        events = {
            (e["event"], e["component"]): e["ns"] - t for e in doc["events"] if e["expert"] == exp
        }
        spans = [
            [v, events["set_end", k]]
            for (name, k), v in sorted(events.items())
            if name == "set_begin"
        ]
        jobs.append(
            dict(
                expert=exp,
                worker=job["worker"],
                slot=job["slot"],
                generation=1,
                enqueue_ns=events["enqueue", -1],
                read_ns=[events["read_begin", -1], events["read_end", -1]],
                set_ns=spans,
                publish_ns=events["publish", -1],
            )
        )
    receipt["job_intervals_relative_to_t0_ns"] = jobs
    return receipt


def audit(a):
    root, study = a.raw, a.study
    outer = loadj(root / "receipt.json")
    need(outer["unit"] == a.unit, "unit")
    result = dict(
        schema="tesy-c291-five-miss-compact-v1",
        status=outer["status"],
        family_sha256=sha(root / "receipt.json"),
        elapsed_s=outer["elapsed_s"],
        terminal_utc=outer["closed_utc"],
        scope_rc=outer.get("scope_rc"),
    )
    if not (root / "detail.json").exists():
        need(outer["status"] == "FAIL_PRESERVED", "absent_detail")
        result["completed_arms"] = 0
        result["evidence"] = "supervisor_ended_without_inner_receipt"
        return result
    detail = loadj(root / "detail.json")
    need(sha(root / "detail.json") == outer["detail_sha256"], "inner_digest")
    result.update(detail_sha256=outer["detail_sha256"], started_arms=outer["arms_started"])
    if outer["status"] != "PASS_C291_MEASURED_FIVE_MISS_FAMILY":
        need(outer["status"] == detail["status"] == "FAIL_PRESERVED", "unknown_terminal")
        result.update(
            completed_arms=sum(
                x.get("status") == "PASS_C291_FIVE_MISS_SERVICE" for x in detail["arms"]
            ),
            evidence="failed_identity_preserved",
            reason=detail.get("reason", "see_private_log").split(":")[0],
            native_receipts_sha256={
                p.parent.parent.name: sha(p) for p in root.glob("*/native/service.json")
            },
        )
        return result
    need(
        detail["status"] == outer["status"]
        and detail["closure"] == "all_36_processes_joined"
        and outer["scope_rc"] == 0,
        "terminal_family",
    )
    src = detail["source_sha256"]
    calc = loadmod(study / "decision.py", src["decision.py"])
    reviewmod = loadmod(study / "review.py", src["review.py"])
    for name, h in src.items():
        need(Path(name).name == name and sha(study / name) == h, "measured_sources")
    need(len(detail["arms"]) == len(calc.schedule()) == 36, "arm_count")
    result.update(
        {
            k: detail[k]
            for k in (
                "commit",
                "tree",
                "build_commit",
                "build_sha256",
                "input_sha256",
                "pack_sha256",
                "numerical_gate_sha256",
                "libraries",
                "executable_sha256",
                "c55_sha256",
                "c118",
                "monitor_provider",
                "source_sha256",
                "peak_bytes",
                "swap_peak_bytes",
                "requested_service_bytes",
                "monitor_samples",
                "prepared_pack_bytes",
                "io_stat",
                "cpu_stat",
                "monitor_sha256",
            )
        }
    )
    arms = []
    missing_prefault = []
    for ix, (key, raw) in enumerate(zip(calc.schedule(), detail["arms"], strict=True), 1):
        b, layout, m = key
        base = root / f"{ix:02d}-{layout}-{m}"
        need(
            raw == loadj(base / "receipt.json")
            and (raw["block"], raw["layout"], raw["observer"]) == key
            and raw["child_started"]
            and raw["child_rc"] == 0
            and raw["status"] == "PASS_C291_FIVE_MISS_SERVICE",
            "per_arm_terminal",
        )
        for name in ["stdout", "stderr"]:
            need(sha(base / name) == raw[name + "_sha256"], "stream_digest")
        nativ = base / "native/service.json"
        need(sha(nativ) == raw["native_receipt_sha256"], "native_digest")
        native = loadj(nativ)
        rev = reviewmod.review_arm(native)
        need(
            rev == raw["review"]
            and rev["publication_ns"] == raw["publish_ns"]
            and rev["outer_ns"] == raw["outer_ns"]
            and rev["resume_ns"] == raw["resume_ns"],
            "replay",
        )
        arm = {
            k: raw[k]
            for k in (
                "block",
                "layout",
                "observer",
                "publish_ns",
                "resume_ns",
                "post_publish_to_resume_ns",
                "outer_ns",
                "prefault_bytes",
                "prefault_ns",
                "requested_bytes",
                "set_count",
                "native_receipt_sha256",
            )
        }
        arm["external_supervisor_spawn_to_exit_s"] = raw["spawn_to_observed_exit_s"]
        if m == "DETAIL":
            arm["decomposition"] = summarize_detail(native, rev)
        if "prefault_faults" not in native:
            missing_prefault.append(ix)
        else:
            fields = native["prefault_faults"]
            need(
                fields["scope"] == "RUSAGE_SELF" and fields == raw["prefault_faults"],
                "prefault_source",
            )
            for k in ("minflt", "majflt"):
                vals = [fields[k + "_" + name] for name in ("before", "after", "delta")]
                need(
                    all(type(x) is int and x >= 0 for x in vals) and vals[1] - vals[0] == vals[2],
                    "prefault_accounting",
                )
            arm["prefault_faults"] = fields
        arms.append(arm)
    need(
        sum(x["requested_bytes"] for x in arms) == result["requested_service_bytes"] == 2379939840,
        "conservation",
    )
    need(
        sum(x["set_count"] for x in arms) == 360
        and result["swap_peak_bytes"] == 0
        and result["peak_bytes"] < 3584 * (1 << 20),
        "SET_count_or_cgroup",
    )
    decision = calc.screen(arms)
    need(decision == outer["assessment"] == detail["assessment"], "decision_changed")
    pairs = audit_pairs(arms, decision)
    result.update(
        arms=arms,
        paired_checks=pairs,
        mechanical_screen_only=decision,
        logical_weight_bytes=36 * 66096000,
        set_requested_bytes=360 * 4406400,
        detail_timing_scope="Intervals relative to native t0, in ns.",
    )
    summary = {}
    for layout in ("DENSE", "STAGED", "DIRECT"):
        summary[layout] = {}
        for mode in ("MIN", "DETAIL"):
            group = [x for x in arms if x["layout"] == layout and x["observer"] == mode]
            summary[layout][mode] = {
                k: spread([x[k] for x in group])
                for k in (
                    "publish_ns",
                    "resume_ns",
                    "outer_ns",
                    "post_publish_to_resume_ns",
                    "prefault_ns",
                )
            }
            if mode == "DETAIL":
                for k in (
                    "read_worker_ns",
                    "set_worker_ns",
                    "read_union_ns",
                    "set_union_ns",
                    "read_or_set_union_ns",
                ):
                    summary[layout][mode][k] = spread([x["decomposition"][k] for x in group])
                summary[layout][mode]["last_experts"] = dict(
                    sorted(
                        collections.Counter(
                            e for x in group for e in x["decomposition"]["last_experts"]
                        ).items()
                    )
                )
    result["arm_dispersion"] = summary
    samples = root / "raw/samples.jsonl"
    inv = detail["c118"]
    need(
        sha(samples) == detail["monitor_sha256"]
        and sha(root / "raw" / f"{a.unit}.start-inventory.jsonl") == inv["sha256"],
        "monitor_hash",
    )
    series = [json.loads(line) for line in samples.read_bytes().splitlines()]
    need(
        len(series) == detail["monitor_samples"] and all(not x["compute_pids"] for x in series),
        "monitor_count_or_GPU",
    )
    result["resource_observations"] = {
        "cpu_max_C": max(x["thermal"]["cpu_tctl_c"] for x in series),
        "gpu_max_C": max(x["gpu"]["temperature_c"] for x in series),
        "nvme_max_C": max(
            t for x in series for t in x["thermal"]["nvme_composite_by_sensor"].values()
        ),
        "host_psi_full_avg10_max": max(
            x["resource_observation"]["host_psi_full_avg10"] for x in series
        ),
        "gpu_compute_observed": False,
        "telemetry_max_gap_s": max(x["gap_s"] for x in series),
        "end_memory_events": detail["cgroup_end"]["events_local"],
    }
    result["original_runner_status"] = result["status"]
    result["missing_prefault_fault_arms"] = missing_prefault
    if missing_prefault:
        result.update(
            status="FAIL_TELEMETRY",
            decision="NOT_ADMISSIBLE",
            accepted_economic_decision=False,
            reason="Cgroup sample coverage does not identify per-process page faults during pretouch",  # noqa: E501
        )
    else:
        result.update(decision=decision["decision"], accepted_economic_decision=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("raw", "study", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    parser.add_argument("--unit", required=True)
    args = parser.parse_args()
    need((args.raw / "receipt.json").is_file(), "nonterminal_family")
    os.umask(0o077)
    dest = args.new_output_dir
    dest.mkdir(exist_ok=False)
    try:
        report = audit(args)
    except Exception as exc:
        (dest / "audit-failed.json").write_text(
            json.dumps({"status": "FAIL_COMPACTION_PRESERVED", "reason": type(exc).__name__}) + "\n"
        )
        raise
    tmp = dest / "receipt.pending"
    with tmp.open("x") as f:
        json.dump(report, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    os.link(tmp, dest / "receipt.json")
    tmp.unlink()
    print(report.get("decision", report["status"]))


if __name__ == "__main__":
    main()
