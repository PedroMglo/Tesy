"""Run one B3 ON 189+3+1 acquisition with the qualified C270 resource supervisor."""

import argparse
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probes = load(HERE / "probes.py", "l25_observer_pins")
P = load(HERE.parent / "profile.py", "l25_private_integrated_profile")
E = P.evaluate
OLD = P.OLD
need, read, sha, save = P.need, P.read, P.sha, P.save
PREVIOUS = "1058221b6735fe7caaaf78f724e2c97b1b54c05983c3ed92bc989893de312aed"
RUNNER = "ad6a79a885171547852b1c2d787258e430d7840f00918b716bccd4c0431b32a9"
AR_DIAGNOSTICS = ("bitwise", "routers_with_gold", "routers_equal", "first")


def select(a):
    need(
        sha(a.parent_build / "receipt.json") == probes.BUILD_SHA
        and sha(a.build_dir / "receipt.json") == a.build_sha256,
        "new and previous build receipts",
    )
    b = read(a.build_dir / "receipt.json")
    prior = read(a.parent_build / "receipt.json")
    child = read(a.build_dir / "client/receipt.json")
    need(
        b["status"] == "PASS_INPUT_L25_OBSERVER_BUILD"
        and b["protocol_sha256"] == probes.PROTOCOL
        and b["physical_parent_build_sha256"] == probes.BUILD_SHA
        and b["worker_commit"] == OLD.WORKER
        and b["static_preflight_sha256"] == a.preflight_sha256
        and b["sources"] == {n: sha(HERE / n) for n in ("build.py", "probes.py", "protocol.md")}
        and b["graph_builds"] == b["model_launches"] == 0
        and b["new_main_tus"] == 1
        and b["model_free_positive_self_tests"] == 2
        and b["smoke"]["status"] == "PASS_LIVE_CANDIDATE"
        and b["smoke"]["objects"] == 18
        and b["candidate_sha256"] == prior["candidate_sha256"] == probes.IMAGE_SHA
        and b["candidate_file"] == prior["candidate_file"] == "candidate/libllama.so.0.0.9884"
        and sha(a.build_dir / b["candidate_file"])
        == sha(a.parent_build / prior["candidate_file"])
        == probes.IMAGE_SHA
        and len(b["startup"]["candidate"]) == 18
        and b["startup"]["candidate"] == prior["startup"]["candidate"]
        and b["prior_client_sha256"] == prior["client_sha256"]
        and b["client_receipt_sha256"] == sha(a.build_dir / "client/receipt.json")
        and child["status"] == "PASS_C269_B3_NUMERIC_BUILD"
        and child["self_test"] == "PASS_B3_NUMERIC_ROW_PLAN"
        and child["parent_capture_source_sha256"] == OLD.SOURCE
        and child["worker_commit"] == OLD.WORKER
        and b["client_sha256"] == child["binary_sha256"] == sha(a.build_dir / "client/b3-numeric")
        and sha(a.build_dir / "client/boundary.cpp")
        == child["native_source_sha256"]
        == hashlib.sha256(probes.render()).hexdigest(),
        "one observer TU / original graph / loader closure",
    )
    return b


def check_prepared(prep, identity):
    need(
        prep["status"] == "PREPARED_ONLY"
        and prep["identity"] == identity
        and prep["model_launch_receipts"] == 0
        and set(prep["arms"]) == {"ON"}
        and prep["arms"]["ON"]["status"] == "PREPARED_ONLY",
        "same one-ON preparation",
    )


def check_observation(report):
    need(
        report["status"] == "MEASURED_L25_INPUTS" and report["neutral"] is True,
        "observer did not reproduce the historical ON",
    )


def comparison_callback(origins, c270, prior_on, grader):
    def compare(cap, mode, ar, unused, old):
        need(mode == "ON" and ar == origins["AR"] and old is OLD, "one ON and same historical AR")
        report = grader.compare(cap, origins["ON"], c270, ar)
        check_observation(report)
        # The qualified run_arm also records four AR diagnostics. The neutral
        # bridge permits carrying over their original independent observations.
        return report | {k: prior_on[k] for k in AR_DIAGNOSTICS}

    return compare


def run(a, out, result):
    need(
        sha(HERE / "protocol.md") == probes.PROTOCOL
        and sha(HERE.parent / "profile.py") == RUNNER
        and HERE.is_relative_to(a.checkout.resolve(strict=True)),
        "frozen observing checkout",
    )
    b = select(a)
    authority = P.Authority(a, b)
    prior_reviewer = load(HERE.parent / "review.py", "l25_previous_pair")
    previous = prior_reviewer.reopen(
        SimpleNamespace(
            family=a.integrated_family,
            family_sha256=probes.FAMILY_SHA,
            archived_family=a.archived_family,
            original_family=a.original_family,
            c270_dir=a.c270_dir,
        )
    )
    need(
        sha(HERE.parent / "receipt.json") == PREVIOUS
        and json.loads(json.dumps(previous)) == read(HERE.parent / "receipt.json"),
        "previous integrated witnesses",
    )
    # reopen() above verified all archived/AR bytes. Reuse their authenticated paths.
    origins = {}
    for mode, path in (("ON", a.integrated_family / "ON"), ("AR", a.archived_family / "AR")):
        member = read(path / "receipt.json")
        unit = member["unit"]
        need(Path(unit).name == unit, "control unit")
        origins[mode] = path / "raw" / (unit + ".capture")
    control, pins = OLD.raw_capture(a.c270_dir)
    prior_on = previous["arms"]["ON"]
    identity = dict(
        commit=a.measurement_commit,
        unit=a.unit + "-on",
        order=["ON"],
        build_sha256=a.build_sha256,
        parent_build_sha256=probes.BUILD_SHA,
        graph_sha256=probes.IMAGE_SHA,
        client_sha256=b["client_sha256"],
        c55_sha256=a.window_sha256,
        preflight_sha256=a.preflight_sha256,
        placement_sha256=sha(a.placement),
        c270_sha256=sha(a.c270_dir / "receipt.json"),
        protocol_sha256=probes.PROTOCOL,
        historical_integrated_sha256=probes.FAMILY_SHA,
        historical_family_sha256=E.HISTORICAL,
        original_family_sha256=E.boundary.OFF_FAMILY,
    )
    result["identity"] = identity
    result.update(
        measurement_commit=a.measurement_commit,
        protocol_sha256=probes.PROTOCOL,
        historical_integrated_sha256=probes.FAMILY_SHA,
        build_sha256=a.build_sha256,
        c55_sha256=a.window_sha256,
    )
    if a.execute:
        need(
            a.prepared_dir
            and a.prepared_sha256
            and sha(a.prepared_dir / "receipt.json") == a.prepared_sha256,
            "prepare authority",
        )
        prep = read(a.prepared_dir / "receipt.json")
        check_prepared(prep, identity)
        need(
            sha(a.prepared_dir / "ON/receipt.json") == prep["arms"]["ON"]["receipt_sha256"],
            "prepare arm",
        )
        result["prepared_sha256"] = a.prepared_sha256

    # Private module instance: the original run_arm executes every admission, C118,
    # monitoring and cleanup check unchanged and calls the new grader once.
    compare = comparison_callback(
        origins, a.c270_dir, prior_on, load(HERE / "grade.py", "l25_new_cuts")
    )
    P.evaluate = SimpleNamespace(compare=compare)
    P.FROZEN = probes.PROTOCOL
    arm, _ = P.run_arm(
        a, out / "ON", "ON", identity["unit"], authority, origins, None, control, pins
    )
    if a.execute:
        report = read(out / "ON/comparison.json")
        check_observation(report)
        old = read(a.integrated_family / "ON/receipt.json")
        need(arm["unique_teacher_match"] == old["unique_teacher_match"], "same teacher trajectory")
        arm["previous_AR_diagnostics"] = {k: arm.pop(k) for k in AR_DIAGNOSTICS}
        arm["observer_neutral"] = True
        result["diagnosis"] = report["diagnosis"]
        result["comparison_sha256"] = arm["comparison_sha256"]
        result["status"] = report["status"]
    else:
        result["status"] = "PREPARED_ONLY"
    save(out / "ON/receipt.json", arm)
    result["arms"]["ON"] = {"status": arm["status"], "receipt_sha256": sha(out / "ON/receipt.json")}
    result["model_launch_receipts"] = arm["model_launch_receipts"]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for k in (
        "checkout",
        "preflight-dir",
        "window",
        "placement",
        "c270-dir",
        "build-dir",
        "parent-build",
        "archived-family",
        "original-family",
        "integrated-family",
        "new-output-dir",
        "prepared-dir",
    ):
        cli.add_argument("--" + k, type=lambda v: Path(v).resolve(), required=k != "prepared-dir")
    for k in (
        "preflight-sha256",
        "window-sha256",
        "build-sha256",
        "measurement-commit",
        "unit",
        "prepared-sha256",
    ):
        cli.add_argument("--" + k, required=k != "prepared-sha256")
    cli.add_argument("--execute", action="store_true")
    a = cli.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    result = dict(status="FAIL_PRESERVED", model_launch_receipts=0, arms={})
    started = time.monotonic()
    try:
        run(a, out, result)
        need(time.monotonic() - started <= 360, "family wall limit")
        need(result["model_launch_receipts"] == int(a.execute), "exactly one measured ON or zero")
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
        if (out / "ON").is_dir():
            folder = out / "ON"
            raw = folder / "raw"
            n = len(list(raw.glob("*.launch.json")))
            if not (folder / "receipt.json").exists():
                save(
                    folder / "receipt.json",
                    dict(
                        status="FAIL_PRESERVED",
                        reason=result["reason"],
                        mode="ON",
                        unit=a.unit + "-on",
                        model_launch_receipts=n,
                        raw_bytes=sum(p.stat().st_size for p in raw.rglob("*") if p.is_file()),
                        boundary_payloads=len(list(raw.glob("*.capture/boundary/*.bin"))),
                    ),
                )
            result["arms"]["ON"] = {
                "status": read(folder / "receipt.json")["status"],
                "receipt_sha256": sha(folder / "receipt.json"),
            }
            result["model_launch_receipts"] = n
    result["wall_s"] = time.monotonic() - started
    save(out / "receipt.json", result)
    print(result["status"], flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
