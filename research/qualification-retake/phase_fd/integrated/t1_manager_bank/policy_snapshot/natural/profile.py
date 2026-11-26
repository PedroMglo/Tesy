"""Acquire two independent R0 C281 sessions with identical PFJ1 and one optional policy sidecar."""

import argparse
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
acq = run_path(HERE / "acquisition.py")
interarm = run_path(HERE / "acquisition_port.py")
conv, controller = acq["conv"], acq["controller"]
need, sha, read, save = conv.need, conv.sha, conv.read, conv.save
BUILD = "4762116405b6f4bf3fee225be62b4485c01228dccc647febdfd36b8515b5d5bc"
IMAGE = "a9920fb2a683bd8912ef2a823fdec2aee305f2c09809693c065a76930b7b5d5b"
TMP = Path("/tmp")


def dependencies(a):
    need(
        sha(acq["INT"] / "t1_capture/controller.py")
        == "01693276b6eca1365c316d2753452ef9e0e4b9ac6e80820902844fd22d87d8d7"
        and sha(acq["INT"] / "t1_capture/audit.py")
        == "8421320989e437594d4026d350269b07c3bb3c0c540a3d79f011a06534480089",
        "T1 controller or PFJ1 conservation",
    )
    build = conv.pinned(a.build_dir / "receipt.json", BUILD)
    need(
        build["candidate_sha256"] == IMAGE
        and build["policy_status"] == "PASS_POLICY_DSO_CPU_BUILD_ONLY"
        and build["fixture_receipt_sha256"] == acq["FIXTURE"]
        and build["static_preflight_sha256"] == a.preflight_sha256
        and build["pfj_control_sha256"] == acq["PFJ_CONTROL"]
        and build["prior_build_sha256"] == conv.BUILD
        and build["program_sha256"] == sha(HERE / "build.py")
        and build["protocol_sha256"] == sha(HERE / "build-protocol.md")
        and build["policy_header_sha256"] == sha(HERE.parent / "snapshot.h"),
        "policy CPU test, candidate and ancestry",
    )
    pins = conv.prior(argparse.Namespace(**(vars(a) | {"build_dir": a.parent_build_dir})))
    return pins, controller["gate"](a), conv.capture.attest_history(a.historical)


def window(a):
    c55 = conv.pinned(a.window / "receipt.json", a.window_sha256)
    pol = conv.pinned(a.window / "resource-policy.json", c55["canonical_policy_sha256"])
    order = conv.window_order(a.window, a.window_sha256, a.build_dir / "receipt.json")
    age = (datetime.now(UTC) - datetime.fromisoformat(pol["snapshot"]["utc"])).total_seconds()
    need(c55["status"] == "PASS_RESOURCE_WINDOW_ONLY" and 0 <= age <= 3600, "C55 age/status")
    return order | {"age_before_C118_s": age}


def arm(a, out, resources, off):
    out.mkdir(mode=0o700)
    rec = {"mode": a.mode, "unit": a.unit, "model_launches": 0}
    start = time.monotonic()
    try:
        rec["c55_order"] = window(a)
        pins, prior, historical = resources
        rt = acq["Runtime"](a, out, historical, pins)
        if a.execute:
            rec.update(rt.execute(a, out))
            need(
                rec["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
                and rec["model_launches"] == 1
                and rec["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
                "C281 client or cleanup",
            )
            acq["after"](a, out, rt, rec, prior)
            if off:
                for field in ("trajectories", "t2_geometry_sha256", "t2_route_sha256"):
                    need(off[field] == rec[field], "contemporary mismatch: " + field)
            rec["status"] = "PASS_C281_NATURAL_POLICY_" + a.mode
        else:
            projected = rt.historical_projection(rt.actual_sources(rt.selection))
            need(
                conv.post.contract.source_digest(projected)
                == read(conv.post.SESSION / "inputs.json")["actual_inputs_sha256"],
                "C281 provenance",
            )
            original, digest = rt.numeric(a.c270)
            rt.bind_c270(a, original, digest)
            _, model = conv.post.contract.placement(a.window, a.placement)
            need(model == original["model_stat"], "placement")
            rec["status"] = "PREPARED_ONLY"
        need(time.monotonic() - start <= 650, "650s arm envelope")
    except Exception as exc:
        rec.update(
            status="FAIL_PRESERVED",
            failure=f"{type(exc).__name__}: {exc}",
            model_launches=len(list(out.glob("raw/*.launch.json"))),
        )
    rec.update(
        envelope_s=time.monotonic() - start,
        build_sha256=BUILD,
        candidate_sha256=IMAGE,
        c55_sha256=a.window_sha256,
        protocol_sha256=sha(HERE / "protocol.md"),
        preflight_sha256=a.preflight_sha256,
        original_c270_sha256=conv.capture.C270,
        parent_numeric_bridge_sha256=a.bridge_sha256,
        prior_on_sha256=controller["PREVIOUS"],
        numeric_evidence_scope="original C270 and parent PFJ1 only",
        commit=a.commit,
    )
    save(out / "receipt.json", rec)
    return rec


def run(a):
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    result = {
        "arms": {},
        "model_launches": 0,
        "commit": a.commit,
        "profile_sha256": sha(__file__),
        "acquisition_sha256": sha(HERE / "acquisition.py"),
        "interarm_program_sha256": sha(HERE / "acquisition_port.py"),
        "interarm_protocol_sha256": sha(HERE / "interarm.md"),
        "protocol_sha256": sha(HERE / "protocol.md"),
        "candidate_sha256": IMAGE,
        "build_sha256": BUILD,
        "window_sha256": a.window_sha256,
    }
    try:
        need(
            conv.post.contract.REPO == a.repo.resolve(strict=True)
            and conv.source.git(a.repo, "rev-parse", "HEAD") == a.commit
            and not conv.source.git(a.repo, "status", "--porcelain")
            and not conv.source.relevant_environment(os.environ),
            "clean committed source/environment",
        )
        result["tree"] = conv.source.git(a.repo, "rev-parse", "HEAD^{tree}")
        args = vars(a) | dict(c270_sha256=conv.capture.C270, build_sha256=BUILD)
        resources = dependencies(a)
        off = None
        for mode in ("OFF", "ON"):
            if mode == "ON" and a.execute:
                gap = {
                    "previous_unit": off["unit"],
                    "previous_native_pid": off["native_ids"]["pid"],
                }
                result["interarm"] = gap
                try:
                    interarm["transition"](
                        conv.source.idle_port,
                        conv.post.contract.PORT,
                        lambda gap=gap: interarm["verify_owner"](
                            gap["previous_unit"], gap["previous_native_pid"]
                        ),
                        gap,
                    )
                finally:
                    save(out / "interarm.json", gap)
                    result["interarm_sha256"] = sha(out / "interarm.json")
            current = argparse.Namespace(
                **(args | {"mode": mode, "unit": a.unit_prefix + "-" + mode.lower()})
            )
            rec = arm(current, out / mode, resources, off)
            result["arms"][mode] = dict(
                receipt_sha256=sha(out / mode / "receipt.json"),
                model_launches=rec["model_launches"],
                status=rec["status"],
            )
            result["model_launches"] += rec["model_launches"]
            need(rec["status"] != "FAIL_PRESERVED", mode + ": " + str(rec.get("failure")))
            if mode == "OFF":
                off = rec
        if a.execute:
            price = conv.paired_cost(off["rows"], rec["rows"])
            result.update(
                status="PASS_C281_NATURAL_POLICY_PAIR",
                paired_cost=price,
                clock_transfer=(
                    "WITHIN_PREREGISTERED_PAIRED_BAND"
                    if price["T2_within_band"]
                    else "INCONCLUSIVE_OUTSIDE_PAIRED_BAND"
                ),
            )
        else:
            result["status"] = "PREPARED_ONLY"
        need(time.monotonic() - start <= 1300, "family exceeded 1300 s")
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", failure=f"{type(exc).__name__}: {exc}")
    result["envelope_s"] = time.monotonic() - start
    save(out / "receipt.json", result)
    print(result["status"], result.get("failure", ""))
    return int(result["status"] == "FAIL_PRESERVED")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    defaults = {
        "placement": "tesy-nvme-placement-20261124-01/receipt.json",
        "c270": "tesy-c270-driver-20261125-r01/receipt.json",
        "historical": "tesy-c281-driver-20261125-r01",
        "preflight-dir": "tesy-env49-static-r01",
        "build-dir": "tesy-policy-natural-build-20261125-r01",
        "parent-build-dir": "tesy-phase-fd-integrated-build-20261125-r01",
        "fixture-dir": "tesy-phase-fd-native-20261125-r02",
        "startup-dir": "tesy-phase-fd-startup-20261125-r01",
        "bridge-dir": "tesy-phase-fd-c270-physical-20261125-r01",
        "prior-on-dir": "tesy-phase-fd-c281-on-20261125-r02",
    }
    for name, folder in defaults.items():
        p.add_argument("--" + name, type=Path, default=TMP / folder)
    for name in ("repo", "new-output-dir", "window"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("unit-prefix", "commit", "window-sha256"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--execute", action="store_true")
    p.set_defaults(
        preflight_sha256="2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16",
        fixture_sha256="215ddd44295755c083f23979ae0c0f183bf3b0f1723d13f7d435f06e5692e954",
        bridge_sha256="9aa14a7cd43197f24f53f3d6169c21a030de34cf83569c09777dd387076984c1",
    )
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
