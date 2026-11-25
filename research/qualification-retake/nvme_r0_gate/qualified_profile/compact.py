"""Recheck a closed C270 qualified profile. All raw paths may be relocated."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath

Q = Path("research/qualification-retake/nvme_r0_gate")
COMMIT = "14b409d75eaa0e6a976fd9b6ebb4b80396ee1df3"
PASS = "PASS_SELECTED_C269_BRIDGE"


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def load(p):
    return json.loads(p.read_bytes())


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def timestamp(s):
    return dt.datetime.fromisoformat(s)


def validate_inventory(root, run_id, pro, launch):
    import c118_start_inventory as c118

    raw = root / "raw"
    ip = raw / (run_id + ".start-inventory.receipt.json")
    receipt = load(ip)
    start = launch["start_inventory"]
    need(sha(ip) == start["receipt_sha256"], "C118 receipt")
    policy = load(root / "resource-policy.json")
    path = raw / (run_id + ".start-inventory.jsonl")
    literal = PurePosixPath(receipt["path"])
    native_raw = PurePosixPath(pro["native_explicit_env"]["LD_DEBUG_OUTPUT"]).parent
    need(literal == native_raw / path.name, "C118 original path relation")
    # Only rebase the location after checking its original binding. Bytes and clock remain original.
    c118.require_inventory(
        root,
        run_id,
        receipt | {"path": str(path)},
        policy=policy,
        cap_bytes=20 << 30,
        expected_power={k: policy["power"][k] for k in ("source", "profile")},
        now=timestamp(start["popen_invoked_utc"]),
        max_age_s=3,
    )
    return {
        "sha256": receipt["sha256"],
        "count": receipt["sample_count"],
        "s": receipt["duration_s"],
        "age_at_spawn_s": (
            timestamp(start["popen_invoked_utc"]) - timestamp(receipt["last_utc"])
        ).total_seconds(),
    }


def audited_origins(repo, root, env, r, p, ident):
    base = repo / Q / "driver_pair"
    helper = module(base / "compact_mixed.py", "archived_c269_log")
    origin = module(base / "driver_origin.py", "qualified_origin")
    pre = load(env / "receipt.json")
    need(
        sha(env / "receipt.json") == p["preflight_sha256"] == r["preflight_sha256"]
        and pre["static_map_sha256"] == sha(env / "static-map.json") == p["static_map_sha256"],
        "static map chain",
    )
    sm = load(env / "static-map.json")
    arm = sm["arms"]["C270"]
    audit = r["authority"]
    data = load(base / "driver_origin.json")
    need(
        pre["status"] == "PASS_STATIC_C270_C281_DRIVER_SELECTION"
        and pre["r02_sha256"] == sha(base / "mixed-r02.json")
        and pre["kernel"] == audit["kernel"] == data["kernel"]
        and pre["deployment_commit"] == audit["deployment_commit"] == origin.COMMIT
        and sm["files"][arm["executable"]]["sha256"]
        == arm["executable_sha256"]
        == r["capture_sha256"],
        "C270 source and signed driver lineage",
    )
    pid = ident["pid"]
    need(
        audit["status"] == "PASS_LIVE_AND_LOADER_C270"
        and audit["live_samples"] > 0
        and audit["native_pid"] == pid
        and audit["preflight_sha256"] == r["preflight_sha256"]
        and audit["static_map_sha256"] == p["static_map_sha256"],
        "native PID evidence",
    )
    log = root / "raw" / ("loader." + str(pid))
    need(sha(log) == audit["loader_sha256"], "native loader file")
    text = log.read_text()
    for line in text.splitlines():
        if line.strip():
            m = re.match(r"\s*(\d+):", line)
            need(m and int(m[1]) == pid, "foreign loader PID")
    drivers = {n: PurePosixPath(t) for n, t in sm["driver_aliases"].items()}
    loaded = helper.archived_initializers(
        text, pid, arm["links"], drivers, sm["files"], audit["initialized_sha256"]
    )
    startup = {t for _, t in arm["links"].values()}
    searches = origin.all_requests(text, pid)
    need(
        startup <= loaded <= startup | set(map(str, drivers.values()))
        and searches <= set(arm["links"]) | set(drivers) | {origin.ABSENT}
        and sorted(searches) == audit["all_search_names"],
        "unknown dependency",
    )
    checks = origin.validate_driver_log(origin.requests(text, pid), loaded, drivers)
    monitor = r["monitor_provider"]
    need(
        checks == audit["driver_providers"]
        and monitor["nvml_sha256"] == pre["nvml_sha256"]
        and monitor["monitor_cli_sha256"] == pre["monitor_cli_sha256"]
        and monitor["driver"] == pre["kernel"]["release"],
        "driver and monitor separation",
    )
    return {
        "kernel": pre["kernel"],
        "deployment": origin.COMMIT,
        "loader_sha256": sha(log),
        "distinct_search_names": len(searches),
        "live_samples": audit["live_samples"],
        "initialized_objects": len(loaded),
        "initializers_sha256": audit["initialized_sha256"],
        "drivers": checks,
        "monitor": monitor,
        "preflight_sha256": r["preflight_sha256"],
        "static_map_sha256": p["static_map_sha256"],
    }


def audit(repo, root, env, prep, gold):
    # A terminal receipt is required before any reads of the run directory.
    terminal = load(root / "receipt.json")
    result = {
        "status": terminal["status"],
        "receipt_sha256": sha(root / "receipt.json"),
        "model_launch_receipts": terminal["model_launch_receipts"],
    }
    need(result["status"] in (PASS, "FAIL_PRESERVED", "PREPARED_ONLY"), "unknown terminal state")
    up = repo / Q
    sys.path.insert(0, str(up))
    sys.path.insert(0, str(repo / "tools"))
    # A FAIL may precede even the creation of protocol.json or the per-run path.
    if result["status"] != PASS:
        launched = list((root / "raw").glob("*.launch.json"))
        need(len(launched) == result["model_launch_receipts"], "launch conservation on failure")
        names = (
            "protocol.json",
            "qualified-protocol.json",
            "argv.json",
            "scope.log",
            "gate.log",
            "selected.json",
        )
        result.update(
            present_sha256={n: sha(root / n) for n in names if (root / n).is_file()},
            error_type=terminal.get("error_type"),
            numerical_gate=terminal.get("numerical_gate", "NOT_RUN"),
            stop_reasons=[
                load(f).get("stop_reason")
                for f in (root / "raw").glob("*.json")
                if f.name not in {g.name for g in launched} and "inventory" not in f.name
            ],
            recovered_launches=len(launched),
        )
        return result
    need(result["model_launch_receipts"] == 1, "PASS requires one launch")
    pro = load(root / "qualified-protocol.json")
    original = load(root / "protocol.json")
    before = load(prep / "receipt.json")
    need(
        before["status"] == "PREPARED_ONLY"
        and before["model_launch_receipts"] == 0
        and before["preflight_sha256"] == pro["preflight_sha256"]
        and before["envelope"] == terminal["envelope"] == "E20_R0"
        and before["capture_sha256"] == terminal["capture_sha256"]
        and load(prep / "qualified-protocol.json")["c55_sha256"] == pro["c55_sha256"]
        and before["qualified_protocol_sha256"] == sha(prep / "qualified-protocol.json")
        and before["protocol_sha256"] == sha(prep / "protocol.json"),
        "unrelated preparation",
    )
    need(
        pro["measurement_commit"] == COMMIT == original["measurement_commit"]
        and pro["base_protocol_sha256"]
        == terminal["protocol_sha256"]
        == sha(root / "protocol.json")
        and pro["base_argv_sha256"] == sha(root / "argv.json")
        and terminal["qualified_protocol_sha256"] == sha(root / "qualified-protocol.json")
        and pro["program_sha256"] == sha(up / "qualified_profile/profile.py")
        and pro["authority_program_sha256"] == sha(up / "qualified_profile/authority.py"),
        "protocol provenance",
    )
    unit = original["execution_scope_unit"]
    need(unit == Path(unit).name and re.fullmatch(r"tesy-[a-z0-9-]+", unit), "invalid unit")
    raw = root / "raw"
    stem = raw / unit
    mp = stem.with_suffix(".json")
    lp = stem.with_suffix(".launch.json")
    m = load(mp)
    launch = load(lp)
    need(
        sha(mp) == terminal["monitor_sha256"]
        and sha(lp) == terminal["launch_sha256"]
        and m["returncode"] == terminal["scope_returncode"] == 0
        and m["stop_reason"] is None
        and m["run_id"] == launch["run_id"] == unit
        and m["process_identity"] == launch["process_identity"]
        and m["start_inventory"] == launch["start_inventory"]
        and m["process_identity"]["cgroup_path"].endswith("/" + unit + ".service")
        and m["binary_sha256"] == launch["binary_sha256"] == terminal["capture_sha256"]
        and launch["executable"] == load(env / "static-map.json")["arms"]["C270"]["executable"]
        and m["command"][0]
        == load(repo / "results/c270-last-use-ordered-fidelity-20261004/protocol.json")["runs"][0][
            "command"
        ][0]
        and m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(root / "protocol.json"),
        "native launch binding",
    )
    import measure

    envs = pro["native_explicit_env"]
    measure.check_monitor(
        m,
        original,
        original["pinned"],
        "E20_R0",
        loader_env={k: envs[k] for k in ("LD_DEBUG", "LD_LIBRARY_PATH", "LD_DEBUG_OUTPUT")},
    )
    for ext, h in m["output_sha256"].items():
        need(
            ext in (".samples.jsonl", ".stderr", ".stdout") and sha(stem.with_suffix(ext)) == h,
            "monitor child artifact",
        )
    need(set(m["output_sha256"]) == {".samples.jsonl", ".stderr", ".stdout"}, "stream inventory")
    events = {k: m["cgroup_end"]["events"][k] - n for k, n in m["cgroup_start"]["events"].items()}
    events_local = {
        k: m["cgroup_end"]["events_local"][k] - n
        for k, n in m["cgroup_start"]["events_local"].items()
    }
    need(
        not any(ev[k] for ev in (events, events_local) for k in ("oom", "oom_kill", "max"))
        and terminal["maxima"] == m["maxima"]
        and m["elapsed_s"] == terminal["elapsed_model_s"],
        "resource record",
    )
    data = audited_origins(repo, root, env, terminal, pro, launch["process_identity"])
    inventory = validate_inventory(root, unit, pro, launch)
    rows = [
        json.loads(line) for line in stem.with_suffix(".samples.jsonl").read_text().splitlines()
    ]
    need(
        rows
        and rows[-1] == m["last_sample"]
        and all(row["process_identity"] == m["process_identity"] for row in rows),
        "per-sample PID",
    )
    grade = load(root / "selected.json")
    need(
        grade == terminal["numerical_gate"]
        and sha(root / "selected.json") == terminal["selected_sha256"]
        and original["gate_sha256"] == sha(repo / "tools/block_layer_reuse_gate.py"),
        "C127 gate",
    )
    measure.check_gate(grade)
    from c94_session_wave_8k_reference import tree_digest
    from c210_witness_gate import qualified

    sealed = load(up / "inputs/receipt.json")
    need(
        original["pinned"]
        == {k: v for k, v in sealed.items() if k not in ("model_forwards", "status")}
        and tree_digest(gold) == sealed["gold"],
        "C127 reference tree",
    )
    old, new = qualified(gold), qualified(raw / (unit + ".capture"))
    for key in ("core", "masks", "logits"):
        need(old[key] == new[key], "independent mismatch in " + key)
    rebuilt = {
        "status": "PASS_PRIVATE_R0_SELECTED_BRIDGE",
        "core_payloads": len(new["core"]),
        "full_logits": len(new["logits"]),
        "prospective_witness": new["prospective_witness"],
    }
    need(json.loads(json.dumps(rebuilt)) == grade, "different independent grade")
    return result | {
        "measurement_commit": COMMIT,
        "envelope": "E20_R0",
        "capture_sha256": terminal["capture_sha256"],
        "selected_sha256": terminal["selected_sha256"],
        "historical_c127_tree": sealed["gold"],
        "numerical_gate": grade,
        "protocol_sha256": sha(root / "protocol.json"),
        "qualified_protocol_sha256": sha(root / "qualified-protocol.json"),
        "scope_log_sha256": sha(root / "scope.log"),
        "gate_log_sha256": sha(root / "gate.log"),
        "preparation_sha256": sha(prep / "receipt.json"),
        "launch_sha256": sha(lp),
        "monitor_sha256": sha(mp),
        "c55_receipt_sha256": pro["c55_sha256"],
        "resource_policy_sha256": sha(root / "resource-policy.json"),
        "c118": inventory,
        "capture_wall_s": m["elapsed_s"],
        "scope_through_cleanup_s": terminal["wall_scoped_s"],
        "start_utc": m["started_utc"],
        "end_utc": m["ended_utc"],
        "raw_bytes": terminal["raw_bytes"],
        "maxima": m["maxima"],
        "cap_bytes": m["cgroup_end"]["memory_max"],
        "high_bytes": m["cgroup_end"]["memory_high"],
        "swap_cap_bytes": m["cgroup_end"]["swap_max"],
        "monitor_samples": len(rows),
        "cgroup_events_delta": events,
        "local_events_delta": events_local,
        "cleanup": {
            "returncode": m["returncode"],
            "stop_reason": m["stop_reason"],
            "child_and_scope_absent_at_profile_close": True,
            "basis": "guarded_run terminal checks",
        },
        "loader": data,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("checkout", "closed-run", "environment-dir", "preparation-dir", "gold-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            audit(
                args.checkout.resolve(),
                args.closed_run.resolve(),
                args.environment_dir.resolve(),
                args.preparation_dir.resolve(),
                args.gold_dir.resolve(),
            ),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
