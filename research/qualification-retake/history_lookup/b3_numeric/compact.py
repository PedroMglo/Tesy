"""Reopen an already terminal B3/AR numerical family, including a relocated private archive."""

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("b3_numeric_offline_profile", HERE / "profile.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
need, read, sha = p.need, p.read, p.sha


def pin(path, expected):
    need(
        path.is_file() and not path.is_symlink() and sha(path) == expected,
        "raw identity " + path.name,
    )
    return read(path)


def tree(path):
    files = sorted(f for f in path.rglob("*") if f.is_file())
    h = hashlib.sha256()
    size = 0
    for f in files:
        need(not f.is_symlink(), "unexpected archive alias")
        n = f.stat().st_size
        h.update(
            f.relative_to(path).as_posix().encode()
            + b"\0"
            + str(n).encode()
            + b"\0"
            + bytes.fromhex(sha(f))
        )
        size += n
    return dict(files=len(files), bytes=size, ordered_name_size_digest_sha256=h.hexdigest())


def phase_names(directory):
    output = {}
    for f in ["initial-pool.bin", "initial-kv.bin", "post3-kv.bin", "native.json"] + [
        name + ".logits.f32" for name in p.ROWS
    ]:
        file = directory / f
        if file.is_file():
            need(not file.is_symlink(), "private witness alias")
            output[f] = dict(bytes=file.stat().st_size, sha256=sha(file))
    return output


def prefix_witness(directory):
    h = hashlib.sha256()
    size = 0
    count = 0
    for f in sorted(directory.glob("prefill*")):
        need(f.is_file() and not f.is_symlink(), "prefill witness type")
        n = f.stat().st_size
        h.update(f.name.encode() + b"\0" + str(n).encode() + b"\0" + bytes.fromhex(sha(f)))
        size += n
        count += 1
    return dict(files=count, bytes=size, ordered_name_size_digest_sha256=h.hexdigest())


def grade_success(folder, unit, arm, material, states):
    mode = arm["mode"]
    rh = folder / "raw"
    src = rh / (unit + ".capture")
    prot = pin(folder / "b3-resource-protocol.json", arm["derived_protocol_sha256"])
    native_cmd = pin(folder / "b3-command.json", arm["execution_argv_sha256"])
    mon = pin(rh / (unit + ".json"), arm["monitor_sha256"])
    lp = pin(rh / (unit + ".launch.json"), arm["launch_sha256"])
    audit = pin(folder / "loader-audit.json", arm["loader_audit_sha256"])
    need(
        mon["process_identity"] == lp["process_identity"]
        and mon["process_identity"]["cgroup_path"].endswith("/" + unit + ".service")
        and mon["command"] == native_cmd["command"][-6:]
        and mon["command"][-2] == mode
        and Path(mon["command"][-1]).name == src.name
        and mon["returncode"] == 0
        and mon["stop_reason"] is None,
        "owned monitored invocation",
    )
    need(
        lp["binary_sha256"] == mon["binary_sha256"] == prot["pinned"]["capture_sha256"]
        and mon["workload_sha256"] == prot["pinned"]["ids_sha256"] == p.IDS
        and prot["scientific_protocol_sha256"] == p.PROTOCOL
        and prot["contrast"] == mode,
        "arm source identity",
    )
    need(
        mon["resource_authority"] == prot["resources"]
        and mon["mapped_libraries_match_ldd"]
        and mon["maxima"] == arm["maxima"]
        and mon["maxima"]["swap_bytes"] == 0
        and mon["maxima"]["direct_model_fds"] > 0
        and arm["live_samples"] > 0
        and mon["artifact_identity"]["stat_at_launch"]
        == mon["artifact_identity"]["stat_at_end"]
        == prot["model_stat"],
        "actual envelope and GGUF",
    )
    for name in ("cgroup_start", "cgroup_end"):
        cg = mon[name]
        need(cg["memory_max"] == cg["memory_high"] == 20 * 2**30 and cg["swap_max"] == 0, "E20 cap")
    st = rh / (unit + ".start-inventory.jsonl")
    need(sha(st) == arm["c118_sha256"] and mon["start_inventory"] == lp["start_inventory"], "C118")
    inventory = pin(
        rh / (unit + ".start-inventory.receipt.json"), mon["start_inventory"]["receipt_sha256"]
    )
    need(
        inventory["sha256"] == sha(st)
        and inventory["duration_s"] >= 60
        and inventory["sample_count"] >= 2
        and inventory["cap_bytes"] == 20 * 2**30,
        "C118 admission sample",
    )
    need(
        sha(rh / ("loader." + str(lp["process_identity"]["pid"]))) == audit["loader_sha256"]
        and audit["initialized_sha256"] == arm["provider_sha256"],
        "runtime loader evidence",
    )
    for suffix, raw_digest in mon["output_sha256"].items():
        need(
            suffix in (".stdout", ".stderr", ".samples.jsonl")
            and sha(rh / (unit + suffix)) == raw_digest,
            "monitor output",
        )
    need(tree(rh)["bytes"] == arm["raw_bytes"] <= 128 * 2**20, "complete raw budget")
    grade = arm["grade"]
    need(
        material["native.json"]["sha256"] == grade["native_sha256"]
        and read(src / "native.json")["initial_state_checked_before_block"] is (mode == "B3")
        and prefix_witness(src) == grade["prefix"]
        and grade["states"] == states,
        "physical state/activations",
    )
    historical = {}
    for name, record in grade["historical"].items():
        rebuilt = p.logits_grade.compare_rows(p.row(src, name), p.row(src, name))
        need(
            record == rebuilt
            and record["reference_sha256"] == prot["pinned"]["gold_full_logits_sha256"][name],
            "historical full row " + name,
        )
        historical[name] = record["reference_sha256"]
    need(
        set(historical) == (set(p.ROWS[:3]) if mode == "AR" else set(p.ROWS[:1])), "historical rows"
    )
    for name in p.ROWS:
        need(material[name + ".logits.f32"]["bytes"] == 804352, "row shape")
    need(
        sha(folder / "resource-policy.json") == prot["start_inventory"]["policy_sha256"],
        "resource policy",
    )
    return dict(
        c118_sha256=arm["c118_sha256"],
        c118_duration_s=inventory["duration_s"],
        c118_samples=inventory["sample_count"],
        monitor_sha256=arm["monitor_sha256"],
        launch_sha256=arm["launch_sha256"],
        loader_sha256=audit["loader_sha256"],
        live_samples=arm["live_samples"],
        full_rows=5,
        logit_values_per_row=201088,
        workload="FIXED_INPUT",
        historical_row_digests=historical,
        prefix=grade["prefix"],
        native_elapsed_s=arm["native_elapsed_s"],
        scope_wall_s=arm["scope_wall_s"],
        maxima=mon["maxima"],
        teacher_greedy_check=arm["unique_teacher_match"],
    )


def arm_report(root, mode, entry):
    folder = root / mode
    raw = folder / "raw"
    arm = pin(folder / "receipt.json", entry["receipt_sha256"])
    need(arm["status"] == entry["status"] and arm["mode"] == mode, "terminal arm status")
    total = len(list(raw.glob("*.launch.json")))
    need(
        total == arm["model_launch_receipts"] == entry["model_launch_receipts"] and total in (0, 1),
        "launch denominator",
    )
    units = [x.name.removesuffix(".launch.json") for x in raw.glob("*.launch.json")]
    if not units and (folder / "prepared.json").is_file():
        units.append(read(folder / "prepared.json")["unit"])
    unit = units[0] if units else None
    directory = raw / (unit + ".capture") if unit else None
    material = phase_names(directory) if directory else {}
    states = {
        f: v
        for f, v in material.items()
        if f in ("initial-pool.bin", "initial-kv.bin", "post3-kv.bin")
    }
    result = dict(
        status=arm["status"],
        mode=mode,
        model_launches=total,
        receipt_sha256=entry["receipt_sha256"],
        files_observed=material,
        private_tree=tree(folder),
        completed_native_receipts=int("native.json" in material),
        complete_F32_files_observed=sum(
            material.get(n + ".logits.f32", {}).get("bytes") == 804352 for n in p.ROWS
        ),
    )
    if arm["status"] == "PASS_NUMERIC_ARM_" + mode:
        need(total == 1 and unit == arm["unit"], "one owned arm required")
        result.update(grade_success(folder, unit, arm, material, states))
    elif arm["status"] == "FAIL_PRESERVED":
        # Files on failure locate the last write. Their values remain unverified.
        if unit and (raw / (unit + ".json")).is_file():
            m = read(raw / (unit + ".json"))
            result["monitor_on_fail"] = {
                "returncode": m["returncode"],
                "stop_reason": m["stop_reason"],
                "sha256": sha(raw / (unit + ".json")),
            }
    else:
        need(arm["status"] == "PREPARED_ONLY" and not total, "unexpected numerical arm state")
    return result, arm, directory


def compact(root, expected):
    receipt = pin(root / "receipt.json", expected)
    need(
        receipt["protocol_sha256"] == p.PROTOCOL and receipt["historical_c270_sha256"] == p.C270,
        "family protocol",
    )
    arms = {}
    records = {}
    paths = {}
    for mode in ("AR", "B3"):
        if mode in receipt["arms"]:
            arms[mode], records[mode], paths[mode] = arm_report(root, mode, receipt["arms"][mode])
        else:
            need(not (root / mode).exists(), "unbound arm directory")
            arms[mode] = dict(
                status="NOT_RUN",
                model_launches=0,
                completed_native_receipts=0,
                complete_F32_files_observed=0,
            )
    status = receipt["status"]
    reopened = {}
    if status in ("PASS_BITS_AND_OBSERVED_STATE", "DIFFERENT_LOGIT_BITS_OR_CARRY_STATE"):
        need(
            all(arms[m]["status"] == "PASS_NUMERIC_ARM_" + m for m in ("AR", "B3")),
            "two completed arms",
        )
        reopened = p.compare_pair(
            paths["AR"], paths["B3"], records["AR"]["grade"], records["B3"]["grade"]
        )
        need(
            reopened == receipt["outcome"] and reopened["status"] == status,
            "offline four-row grading",
        )
    else:
        need(status in ("FAIL_PRESERVED", "PREPARED_ONLY"), "unrecognized family")
    return dict(
        status=status,
        raw_receipt_sha256=expected,
        profile_sha256=receipt["program_sha256"],
        measurement_commit=receipt["measurement_commit"],
        build_sha256=receipt["build_sha256"],
        c55_sha256=receipt["c55_sha256"],
        protocol_sha256=p.PROTOCOL,
        model_launches=sum(a["model_launches"] for a in arms.values()),
        measured_arms=sum(a["completed_native_receipts"] for a in arms.values()),
        arms=arms,
        paired_outcome=reopened,
        historical_c270_sha256=p.C270,
        family_wall_s=receipt["envelope_s"],
        private_family_tree=tree(root),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--family-sha256", required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = compact(a.family, a.family_sha256)
    except Exception as exc:
        result = {"status": "FAIL_OFFLINE_AUDIT", "failure": type(exc).__name__ + ": " + str(exc)}
    p.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_OFFLINE_AUDIT")


if __name__ == "__main__":
    raise SystemExit(main())
