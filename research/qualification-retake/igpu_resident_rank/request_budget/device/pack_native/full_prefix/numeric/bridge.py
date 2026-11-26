"""Reopen the two real C292 capture trees and bind them to the full-prefix ELF."""

import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "numeric/profile.py"
PARENT = "933c002f66a534f44ff9f96a08a81c475fe4bed824d5a6eac0dbd5acfb28e622"
MODES = ("overlay_off", "overlay_on")


def checked(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"receipt integrity: {path.name}")
    return json.loads(data)


def previous():
    if hashlib.sha256(OLD.read_bytes()).hexdigest() != PARENT:
        raise ValueError("historical C292 evaluator")
    return run_path(str(OLD))


def verify_natural_gate(bridge_dir, sha, build_dir, build_sha):
    bridge_dir, build_dir = Path(bridge_dir), Path(build_dir)
    p = previous()
    need = p["need"]
    family = checked(bridge_dir / "receipt.json", sha)
    b = checked(build_dir / "receipt.json", build_sha)
    need(
        family["status"] == "PASS_C292_FULL_PREFIX_NUMERIC"
        and family["build_receipt_sha256"] == build_sha
        and family["candidate_sha256"] == b["candidate_sha256"]
        and b["status"] == "PASS_C291_FULL_PREFIX_DSO_STATIC_C281"
        and family["model_launch_receipts"] == 2
        and not family["unexecuted_arms"]
        and set(family["arms"]) == set(MODES),
        "complete full-prefix C292 family",
    )
    for mode in MODES:
        record = family["arms"][mode]
        folder = bridge_dir / mode
        arm = checked(folder / "receipt.json", record["receipt_sha256"])
        enabled = mode == "overlay_on"
        need(
            arm["status"] == "PASS_C292_ARM_NUMERICS"
            and arm["cleanup"]
            and arm["journal_enabled"] == enabled
            and arm["image_sha256"] == b["candidate_sha256"]
            and arm["build_receipt_sha256"] == build_sha
            and arm["model_launch_receipts"] == 1
            and all(
                arm[k] == record[k] for k in ("capture_tree", "image_sha256", "journal_enabled")
            ),
            "C292 arm/ELF identity",
        )
        raw = folder / "raw"
        launch = checked(raw / (arm["unit"] + ".launch.json"), arm["launch_sha256"])
        monitor = checked(raw / (arm["unit"] + ".json"), arm["monitor_sha256"])
        tree = p["grade"].tree_digest(raw / (arm["unit"] + ".capture"))
        need(
            launch["process_identity"] == monitor["process_identity"]
            and monitor["returncode"] == 0
            and tree == arm["capture_tree"] == family["independent_reference"]["capture_tree"],
            "C292 process and numerical tree",
        )
    return family
