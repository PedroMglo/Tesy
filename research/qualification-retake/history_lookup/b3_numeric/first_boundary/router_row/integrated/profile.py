"""Two serial B3 scopes reproducing OFF and testing the three-column router ON."""

import argparse
import copy
import hashlib
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import binding  # noqa: E402
import evaluate  # noqa: E402
from binding import FLAG, OLD, Authority  # noqa: E402

builder = evaluate.load(HERE / "build.py", "integrated_router_build")
need, read, sha, save = OLD.need, OLD.read, OLD.sha, OLD.save
FROZEN = builder.PROTO


def select(a):
    need(sha(a.build_dir / "receipt.json") == a.build_sha256, "build receipt")
    b = read(a.build_dir / "receipt.json")
    e = read(a.build_dir / "client/receipt.json")
    need(
        b["status"] == "PASS_INTEGRATED_ROUTER_BUILD"
        and b["protocol_sha256"] == FROZEN
        and b["worker_commit"] == OLD.WORKER
        and b["static_preflight_sha256"] == a.preflight_sha256
        and b["sources"] == {n: sha(HERE / n) for n in builder.SOURCE_NAMES}
        and b["original_sha256"] == binding.library.ORIGINAL
        and b["reused_objects"] == 165
        and b["smoke"]["status"] == "PASS_LIVE_CANDIDATE"
        and b["smoke"]["objects"] == 18
        and not b["relink_alloc_differences"]
        and b["candidate_alloc_differences"]
        and b["client_receipt_sha256"] == sha(a.build_dir / "client/receipt.json")
        and e["status"] == "PASS_C269_B3_NUMERIC_BUILD"
        and e["self_test"] == "PASS_B3_NUMERIC_ROW_PLAN"
        and e["parent_capture_source_sha256"] == OLD.SOURCE
        and e["binary_sha256"] == b["client_sha256"]
        and e["native_source_sha256"] == hashlib.sha256(builder.source.client()).hexdigest()
        and b["model_launches"] == 0,
        "integrated graph/observer provenance",
    )
    return b


def run_arm(a, folder, mode, unit, authority, origins, later, c270, pins):
    folder.mkdir()
    raw = folder / "raw"
    base_args = copy.copy(a)
    base_args.unit, base_args.execute = unit, False
    prepared = OLD.base.prepare_campaign(base_args, folder)
    need(prepared["status"] == "PREPARED_ONLY", "C270 resource admission")
    initial = read(folder / "qualified-protocol.json")
    protocol = read(folder / "protocol.json")
    need(
        protocol["pinned"] == pins and sha(authority.template_exe) == pins["capture_sha256"],
        "C270 input control",
    )
    sealed = copy.deepcopy(pins)
    for key in ("numerical_dso_sha256", "startup_dso_sha256"):
        need(sealed[key][authority.image.name] == binding.library.ORIGINAL, "original closure")
        sealed[key][authority.image.name] = authority.image_sha
    sealed["capture_sha256"] = authority.arm["executable_sha256"]
    protocol.update(
        pinned=sealed,
        scientific_protocol_sha256=FROZEN,
        experimental_mode=mode,
        schema="tesy-b3-router-row-v1",
    )
    spec = folder / "integrated-resource.json"
    save(spec, protocol)
    native_mode = "AR" if mode == "AR" else "B3"
    gold = Path(initial["check"][-1]).resolve(strict=True)
    child_gold = gold if mode == "AR" else origins["AR"]
    cmd = OLD.derivative_command(
        initial["monitor"],
        authority.template_exe,
        authority.exe,
        child_gold,
        native_mode,
        unit,
        spec,
    )
    cmd = binding.adjust(cmd, a.checkout, authority.original_search, authority.native_search, mode)
    env = initial["native_explicit_env"] | authority.child_env(raw / "loader")
    if mode == "ON":
        env[FLAG] = "1"
    teacher = OLD.teacher_prefix(Path(cmd[-4]))
    save(
        folder / "command.json",
        dict(command=cmd, env=env, parent_sha256=sha(folder / "qualified-protocol.json")),
    )
    record = dict(
        status="PREPARED_ONLY",
        unit=unit,
        mode=mode,
        model_launch_receipts=0,
        build_sha256=a.build_sha256,
        command_sha256=sha(folder / "command.json"),
        resource_sha256=sha(spec),
        client_sha256=sealed["capture_sha256"],
        library_sha256=authority.image_sha,
    )
    save(folder / "prepared.json", record)
    if not a.execute:
        return record, None
    import measure
    import run_bounded

    record["monitor_provider"] = authority.monitor_proof()
    need(run_bounded.file_identity(Path(cmd[-5])) == protocol["model_stat"], "model identity")
    ident, n, seen, wall = OLD.base.guarded_run(cmd, folder, unit, authority, measure, run_bounded)
    mp = raw / (unit + ".json")
    lp = raw / (unit + ".launch.json")
    manifest = read(mp)
    need(
        manifest["process_identity"] == ident == read(lp)["process_identity"]
        and manifest["command"] == cmd[-6:],
        "native invocation",
    )
    binding.monitor_check(manifest, protocol, env, mode, measure)
    audit = authority.audit(raw / "loader", ident["pid"])
    need(
        set(audit["initialized_sha256"]) >= {Path(z).name for z in seen}
        and audit["initialized_sha256"][authority.image.name] == authority.image_sha
        and str(authority.image) in seen
        and measure.file_bytes(raw) <= 128 * OLD.MIB
        and wall <= 320,
        "live authority or budget",
    )
    save(folder / "loader-audit.json", audit)
    path = raw / (unit + ".capture")
    original = OLD.require_arm(path, native_mode, gold, pins["gold_full_logits_sha256"])
    for label, r in original["historical"].items():
        need(r["reference_sha256"] == sha(OLD.row(c270, label)), "C270 reference")
    ref = "B3" if mode == "OFF" else "AR"
    observation = evaluate.compare(path, mode, origins[ref], later, OLD)
    save(folder / "comparison.json", observation)
    if mode in {"OFF", "AR"}:
        need(observation["bitwise"], "failed archived same-mode observation or state bridge")
    record.update(
        status="OBSERVED_" + mode,
        model_launch_receipts=1,
        grade=original,
        comparison_sha256=sha(folder / "comparison.json"),
        bitwise=observation["bitwise"],
        routers_with_gold=observation["routers_with_gold"],
        routers_equal=observation["routers_equal"],
        first=observation["first"],
        unique_teacher_match=OLD.next_ids_match(path, teacher),
        maxima=manifest["maxima"],
        monitor_sha256=sha(mp),
        launch_sha256=sha(lp),
        loader_sha256=sha(folder / "loader-audit.json"),
        live_samples=n,
        scope_wall_s=wall,
        native_elapsed_s=manifest["elapsed_s"],
        raw_bytes=measure.file_bytes(raw),
        c118_sha256=sha(raw / (unit + ".start-inventory.jsonl")),
    )
    return record, path


def prior_pair(a):
    need(
        a.completed_pair_sha256
        and sha(a.completed_pair / "receipt.json") == a.completed_pair_sha256,
        "optional AR pair authority",
    )
    r = read(a.completed_pair / "receipt.json")
    need(
        r["status"] == "RESTORED_86_AND_FULL_OUTPUTS"
        and r["model_launch_receipts"] == 2
        and r["build_sha256"] == a.build_sha256
        and r["protocol_sha256"] == FROZEN
        and r["historical_family_sha256"] == evaluate.HISTORICAL,
        "optional AR is not admissible",
    )
    for mode in ("OFF", "ON"):
        d = a.completed_pair / mode
        need(sha(d / "receipt.json") == r["arms"][mode]["receipt_sha256"], "prior arm hash")
        rec = read(d / "receipt.json")
        need(
            rec["bitwise"]
            and rec["status"] == "OBSERVED_" + mode
            and rec["model_launch_receipts"] == 1
            and sha(d / "comparison.json") == rec["comparison_sha256"],
            "prior scientific gate",
        )
    rec = read(a.completed_pair / "ON/receipt.json")
    cap = a.completed_pair / "ON/raw" / (rec["unit"] + ".capture")
    need(
        evaluate.boundary.check_arm(cap, "B3", evaluate.cuts("ON"))
        == read(a.completed_pair / "ON/comparison.json")["coverage"],
        "prior ON bytes",
    )
    return cap


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "checkout",
        "preflight-dir",
        "window",
        "placement",
        "c270-dir",
        "build-dir",
        "archived-family",
        "original-family",
        "new-output-dir",
        "prepared-dir",
        "completed-pair",
    ):
        p.add_argument("--" + k, type=Path, required=k not in ("prepared-dir", "completed-pair"))
    for k in (
        "preflight-sha256",
        "window-sha256",
        "measurement-commit",
        "unit",
        "build-sha256",
        "prepared-sha256",
        "completed-pair-sha256",
    ):
        p.add_argument("--" + k, required=k not in ("prepared-sha256", "completed-pair-sha256"))
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    a.checkout = a.checkout.resolve(strict=True)
    started = time.monotonic()
    result = dict(
        status="FAIL_PRESERVED",
        arms={},
        model_launch_receipts=0,
        measurement_commit=a.measurement_commit,
        build_sha256=a.build_sha256,
        protocol_sha256=FROZEN,
        c55_sha256=a.window_sha256,
        historical_family_sha256=evaluate.HISTORICAL,
        original_family_sha256=evaluate.boundary.OFF_FAMILY,
        optional_pair_sha256=a.completed_pair_sha256,
    )
    try:
        need(
            sha(HERE / "protocol.md") == FROZEN and HERE.is_relative_to(a.checkout),
            "frozen checkout",
        )
        b = select(a)
        authority = Authority(a, b)
        evaluate.boundary.historical(a.original_family)
        origins = evaluate.reference(a.archived_family)
        later = evaluate.later_reference(a.c270_dir)
        c270, pins = OLD.raw_capture(a.c270_dir)
        need(len(later) == 176, "late reference rows")
        previous = prior_pair(a) if a.completed_pair else None
        modes = ("AR",) if previous else ("OFF", "ON")
        if a.execute:
            need(
                a.prepared_dir and sha(a.prepared_dir / "receipt.json") == a.prepared_sha256,
                "prepared receipt hash",
            )
            prep = read(a.prepared_dir / "receipt.json")
            need(
                prep["status"] == "PREPARED_ONLY"
                and set(prep["arms"]) == set(modes)
                and all(
                    prep[k] == v
                    for k, v in result.items()
                    if k not in {"status", "arms", "model_launch_receipts"}
                ),
                "same preparation",
            )
            result["prepared_sha256"] = a.prepared_sha256
        for mode in modes:
            folder, unit = out / mode, a.unit + "-" + mode.lower()
            try:
                record, cap = run_arm(a, folder, mode, unit, authority, origins, later, c270, pins)
                if a.execute and mode == "AR":
                    third = evaluate.complete_third(cap, previous)
                    save(folder / "all-routers.json", third)
                    record.update(
                        complete_108=third["all_108"],
                        all_routers_sha256=sha(folder / "all-routers.json"),
                    )
                need(time.monotonic() - started <= 720, "family wall")
            except Exception as exc:
                folder.mkdir(exist_ok=True)
                raw = folder / "raw"
                record = dict(
                    status="FAIL_PRESERVED",
                    reason=f"{type(exc).__name__}: {exc}",
                    unit=unit,
                    mode=mode,
                    model_launch_receipts=len(list(raw.glob("*.launch.json"))),
                    raw_bytes=sum(z.stat().st_size for z in raw.rglob("*") if z.is_file()),
                    boundary_payloads=len(list(raw.glob("*.capture/boundary/*.bin"))),
                )
                if (folder / "comparison.json").is_file():
                    record["comparison_sha256"] = sha(folder / "comparison.json")
                    record["first"] = read(folder / "comparison.json")["first"]
                raise
            finally:
                save(folder / "receipt.json", record)
                result["arms"][mode] = {k: record[k] for k in ("status", "model_launch_receipts")}
                result["arms"][mode]["receipt_sha256"] = sha(folder / "receipt.json")
                result["model_launch_receipts"] += record["model_launch_receipts"]
        if not a.execute:
            result["status"] = "PREPARED_ONLY"
        elif previous:
            result["status"] = "RESTORED_108" if record["complete_108"] else "DIFFERENT_IN_EXTRA_22"
        else:
            result["status"] = (
                "RESTORED_86_AND_FULL_OUTPUTS"
                if record["bitwise"]
                else "DIFFERENT_AT_OBSERVED_CUT_OR_OUTPUT"
            )
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result["wall_s"] = time.monotonic() - started
    save(out / "receipt.json", result)
    print(result["status"], flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
