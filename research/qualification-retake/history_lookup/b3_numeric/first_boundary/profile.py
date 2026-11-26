"""Authorize two independent E20 arms with each immediately gated by its archived OFF result."""

import argparse
import hashlib
import importlib.util
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import grade  # noqa: E402
from render import render  # noqa: E402

PROTOCOL = "ca068fdb0ba0bcdc4034c6274cf92e1185c31160582b2636dfc183d0639120a5"
BASE_PROFILE = "5656ee0d497d412a32e18181c0209e3ec225c50fe8ce74b69da8851b03e99792"
need, sha = grade.need, grade.sha


def parent():
    path = HERE.parent / "profile.py"
    need(sha(path) == BASE_PROFILE, "original B3 acquisition")
    spec = importlib.util.spec_from_file_location("b3_boundary_base", path)
    src = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(src)
    src.PROTOCOL = PROTOCOL
    return src


def select(a, old):
    receipt = a.build_dir / "receipt.json"
    need(sha(receipt) == a.build_sha256, "build identity")
    b = old.read(receipt)
    expected_sources = {k: sha(HERE / k) for k in build.SOURCES}
    need(
        b["status"] == "PASS_FIRST_BOUNDARY_BUILD"
        and b["inputs"] == expected_sources
        and b["worker_commit"] == old.WORKER
        and b["static_preflight_sha256"] == a.preflight_sha256
        and b["c269_startup_objects"] == len(b["startup_objects"]) == 18
        and b["parent_capture_source_sha256"] == old.SOURCE
        and b["original_builder_sha256"] == build.BASE_BUILD
        and b["executable"] == "b3-numeric"
        and b["model_launches"] == 0
        and b["self_test"] == "PASS_B3_NUMERIC_ROW_PLAN"
        and b["native_source_sha256"] == hashlib.sha256(render()).hexdigest(),
        "derived binary provenance",
    )
    exe = (a.build_dir / b["executable"]).resolve(strict=True)
    need(sha(exe) == b["binary_sha256"], "derived executable digest")
    return exe, b["binary_sha256"]


def observed_before_failure(folder, mode, unit):
    raw = folder / "raw"
    cap = raw / (unit + ".capture")
    observed = {}
    for name, expected in grade.old_rows()[mode]["files_observed"].items():
        path = cap / name
        if path.is_file():
            observed[name] = {
                "bytes": path.stat().st_size,
                "matches_off": sha(path) == expected["sha256"],
            }
    return {
        "model_launch_receipts": len(list(raw.glob("*.launch.json"))),
        "raw_bytes": sum(p.stat().st_size for p in raw.rglob("*") if p.is_file()),
        "boundary_payloads": len(list((cap / "boundary").glob("*.bin"))),
        "available_off_bridges": observed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "checkout",
        "preflight-dir",
        "window",
        "placement",
        "c270-dir",
        "build-dir",
        "archived-family",
        "new-output-dir",
        "prepared-dir",
    ):
        parser.add_argument("--" + key, type=Path, required=key != "prepared-dir")
    for key in (
        "preflight-sha256",
        "window-sha256",
        "measurement-commit",
        "unit",
        "build-sha256",
        "prepared-sha256",
    ):
        parser.add_argument("--" + key, required=key != "prepared-sha256")
    parser.add_argument("--execute", action="store_true")
    a = parser.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    old = parent()
    started = time.monotonic()
    result = {
        "status": "FAIL_PRESERVED",
        "arms": {},
        "measurement_commit": a.measurement_commit,
        "build_sha256": a.build_sha256,
        "c55_sha256": a.window_sha256,
        "protocol_sha256": PROTOCOL,
        "program_sha256": sha(Path(__file__)),
        "historical_family_sha256": grade.OFF_FAMILY,
    }
    try:
        need(
            sha(HERE / "protocol.md") == PROTOCOL and HERE.is_relative_to(a.checkout.resolve()),
            "frozen checkout",
        )
        exe, exe_sha = select(a, old)
        result["binary_sha256"] = exe_sha
        result["archived_witnesses"] = grade.historical(a.archived_family)
        control, pins = old.raw_capture(a.c270_dir)
        if a.execute:
            need(
                a.prepared_dir is not None
                and sha(a.prepared_dir / "receipt.json") == a.prepared_sha256,
                "prepared admission",
            )
            prep = old.read(a.prepared_dir / "receipt.json")
            need(
                prep["status"] == "PREPARED_ONLY"
                and all(prep[k] == v for k, v in result.items() if k not in ("arms", "status")),
                "changed admission since preparation",
            )
            result["prepared_sha256"] = a.prepared_sha256
        paths = {}
        paired = None
        for mode in ("AR", "B3"):
            folder, unit = out / mode, a.unit + "-" + mode.lower()
            try:
                arm, path = old.run_arm(a, folder, unit, mode, exe, exe_sha, control, pins, paired)
                if a.execute:
                    status = grade.bridge(path, mode)
                    arm["same_mode_off"] = status
                    need(status["bitwise"], "instrumented trajectory differs from same-mode OFF")
                    arm["coverage"] = grade.check_arm(path, mode)
                if mode == "AR":
                    paired = (folder / "raw" / (unit + ".capture"), arm)
                paths[mode] = path
                need(time.monotonic() - started <= 720, "family wall")
            except Exception as exc:
                folder.mkdir(exist_ok=True)
                arm = dict(
                    status="FAIL_PRESERVED",
                    reason=f"{type(exc).__name__}: {exc}",
                    **observed_before_failure(folder, mode, unit),
                )
                old.save(folder / "receipt.json", arm)
                result["arms"][mode] = {k: arm[k] for k in ("status", "model_launch_receipts")}
                result["arms"][mode]["receipt_sha256"] = sha(folder / "receipt.json")
                raise
            old.save(folder / "receipt.json", arm)
            result["arms"][mode] = {k: arm[k] for k in ("status", "model_launch_receipts")}
            result["arms"][mode]["receipt_sha256"] = sha(folder / "receipt.json")
        if a.execute:
            report = grade.compare(paths["AR"], paths["B3"])
            old.save(out / "comparison.json", report)
            result.update(
                status=report["status"],
                comparison_sha256=sha(out / "comparison.json"),
                first=report["first"],
                per_position=report["per_position"],
            )
        else:
            result["status"] = "PREPARED_ONLY"
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result["wall_s"] = time.monotonic() - started
    old.save(out / "receipt.json", result)
    print(result["status"], flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
