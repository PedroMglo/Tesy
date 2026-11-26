"""Reopen the four archived P sessions, their launches, client streams and natural pack journal."""

import argparse
import json
import os
import sys
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace


def review(a):
    sys.path.insert(0, str(a.source))
    import family as f

    q = f.acquisition
    passive = q.pinned(a.family / "family.json", a.family_sha256)
    q.need(passive["status"] == "COMPLETED_PACK_NATURAL_OBSERVATION", "terminal family")
    proof = q.pinned(a.prepared / "family.json", passive["prepared_sha256"])
    identity = passive["identity"]
    c55 = q.pinned(a.window / "receipt.json", identity["args"]["window_sha256"])
    q.need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and c55["gpu_compute_max"] == 0
        and q.sha(a.window / "samples.jsonl") == c55["window_sha256"]
        and q.sha(a.window / "resource-policy.json") == c55["canonical_policy_sha256"],
        "C55 seal",
    )
    labels = list(q.MODES)
    q.need(
        proof["status"] == f.PREPARED
        and proof["identity"] == identity
        and labels == identity["order"]
        and passive["model_launches"] == 4
        and passive["requests"] == 8
        and set(passive["arms"]) == set(labels),
        "family lineage",
    )
    q.need(
        all(q.sha(a.source / name) == value for name, value in identity["sources"].items()),
        "review source identity",
    )
    auditor = a.source.parent / "natural_trace/analyse.py"
    q.need(q.sha(auditor) == identity["journal_auditor_sha256"], "journal auditor")
    args = SimpleNamespace(
        build_dir=a.build, build_sha256=identity["args"]["build_sha256"], history_dir=a.history
    )
    summary = {}
    trace_metrics = None
    process_ids = set()
    for i, name in enumerate(labels):
        out = a.family / name
        pre = q.pinned(a.prepared / name / "arm.json", proof["arms"][name]["sha256"])
        q.need(
            pre == proof["arms"][name]["arm"]
            and pre["mode"] == name
            and pre["status"] == "PREPARED_ONLY"
            and pre["profile"]["model_launches"] == 0,
            "prepared arm seal",
        )
        arm = q.pinned(out / "arm.json", passive["arms"][name]["sha256"])
        q.need(
            arm == passive["arms"][name]["arm"]
            and arm["mode"] == name
            and arm["status"] == "PASS_ONE_NATURAL_ARM",
            "terminal arm",
        )
        result = q.pinned(out / "receipt.json", arm["receipt_sha256"])
        grade = f.graded(out, result, args, name)
        for turn in grade["rows"]:
            n, seconds = turn["predicted_n"], turn["decode_s"]
            turn["server_ms_per_output"] = 1000 * seconds / n
            turn["native_evaluations_after_first"] = n - 1
            turn["decode_ms_per_post_first_evaluation"] = 1000 * seconds / (n - 1)
        q.need(arm["grade"] == grade, "published arm grade changed")
        obs = result["pack_events"]
        trace, trigger = out / "raw/events.pfj", out / "raw/T2.trigger"
        if name == "ON":
            q.need(
                q.sha(trace) == obs["journal_sha256"]
                and trigger.is_file()
                and trigger.stat().st_size == 0
                and len(obs["journal_fd_cuts"]) == 2
                and obs["journal_fd_cuts"][0] == obs["journal_fd_cuts"][1]
                and obs["journal_fd_cuts"][0]["fd"] >= 0,
                "pack trigger or native journal",
            )
            journal = run_path(auditor)["audit_arm"](out, result, obs["before_second_ns"])
            recorded = q.pinned(out / "journal-audit.json", arm["journal_audit_sha256"])
            # Re-read JSON to normalize tuple/list and int keys in identical representations.
            q.need(recorded == json.loads(json.dumps(journal)), "published journal grade changed")
            trace_metrics = {k: recorded[k] for k in ("status", "route", "budget", "coverage")}
            trace_metrics["job_counts"] = recorded["jobs"]["counts"]
            trace_metrics["calls"] = len(recorded["calls"])
            trace_metrics["journal_audit_sha256"] = arm["journal_audit_sha256"]
        else:
            q.need(
                not os.path.lexists(trace)
                and not os.path.lexists(trigger)
                and obs["journal_fd_cuts"] == [None, None]
                and obs["journal_sha256"] is None,
                "inactive observer wrote a journal",
            )
        unit = identity["args"]["unit_prefix"] + "-" + name.lower()
        launch = q.read(out / "raw" / (unit + ".launch.json"))
        pid = launch["process_identity"]["pid"]
        process_ids.add(pid)
        q.need(result["runtime_authority"]["native_pid"] == pid, "native process")
        if i < 3:
            closed = q.read(a.family / (name + "-closed-endpoint.json"))
            q.need(
                closed["previous"] == name
                and closed["pid"] == pid
                and closed["bind_available"] is True
                and closed["limit_s"] == 75
                and all(set(s["tcp_states"]) <= {"06"} for s in closed["samples"])
                and closed["elapsed_s"] == passive["closed_endpoint_wait_s"][labels[i + 1]],
                "strict port transition",
            )
        summary[name] = {
            "arm_sha256": passive["arms"][name]["sha256"],
            "receipt_sha256": arm["receipt_sha256"],
            "image_sha256": result["transport"]["libllama"]["sha256"],
            "journal_status": arm["journal_status"],
            "journal_sha256": obs["journal_sha256"],
            "terminal_cleanup": result["cleanup"],
            "shutdown": grade["transport"]["shutdown"],
            "c55_age_at_spawn_s": result["transport"]["c55_age_at_spawn_s"],
            "resources": {
                k: grade[k]
                for k in (
                    "maxima",
                    "energy",
                    "cgroup_cap_bytes",
                    "preventive_stop_bytes",
                    "start_window_span_s",
                    "start_window_age_at_popen_s",
                    "native_monitor_elapsed_s",
                    "ready_s",
                    "envelope_s",
                    "monitor_sha256",
                )
            },
            "turns": [
                {
                    k: t[k]
                    for k in (
                        "label",
                        "input_n",
                        "predicted_n",
                        "prefill_s",
                        "decode_s",
                        "decode_tok_s",
                        "first_final_s",
                        "transport_complete_s",
                        "frames",
                        "validated_terminal_s",
                        "functional",
                        "prefix",
                        "sampled_ids_sha256",
                        "stable_frames_sha256",
                        "official_ids_sha256",
                    )
                }
                for t in grade["rows"]
            ],
        }
    paired = f.compare(passive["arms"], labels)
    q.need(
        len(process_ids) == len(labels) and paired == passive["paired"],
        "independent PID or price reconciliation",
    )
    return dict(
        status="REPRODUCED_PACK_OBSERVER_C281_FAMILY",
        family_sha256=a.family_sha256,
        prepared_sha256=passive["prepared_sha256"],
        model_launches_by_review=0,
        reviewed_launches=4,
        reviewed_requests=8,
        journal_status=passive["journal_status"],
        c55_sha256=identity["args"]["window_sha256"],
        c55_samples=c55["samples"],
        c55_span_s=c55["span_s"],
        c55_cap_max_bytes=c55["canonical_memory"]["cap_max_bytes"],
        family_elapsed_s=passive["elapsed_s"],
        port_waits_s=passive["closed_endpoint_wait_s"],
        numeric_bridge_sha256=identity["bridge_sha256"],
        build_sha256=identity["args"]["build_sha256"],
        arms=summary,
        paired=paired,
        trace=trace_metrics,
    )


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--source", type=Path, default=Path(__file__).resolve().parent)
    for name in ("family", "prepared", "build", "history", "window", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--family-sha256", required=True)
    a = cli.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        row = review(a)
    except Exception as exc:
        row = dict(
            status="FAIL_PRESERVED",
            reason=f"{type(exc).__name__}: {exc}",
            family_sha256=a.family_sha256,
        )
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(row, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(row["status"], row.get("reason", ""))
    return int(row["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
