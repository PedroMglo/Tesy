import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from family import acquisition as ac  # noqa: E402


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True))
    return ac.sha(path)


def example(root):
    old, new, fds = [root / part for part in ("old", "new", "fd")]
    evidence = {"positive_samples": 4}
    ident = {"pid": 41, "start_ticks": 1240}
    unit = "original-control"
    a = SimpleNamespace(
        bridge_dir=new,
        bridge_failed_dir=old,
        bridge_fds_dir=fds,
        bridge_review=root / "verified.json",
        build_sha256="build",
    )
    why = "KeyError: 'startup_count'"
    raw = old / "control_off/raw"
    launch = put(raw / (unit + ".launch.json"), {"process_identity": ident})
    proof = {
        "process_identity": ident,
        "launch_sha256": launch,
        "status": "PASS_LIVE_CONTROL_OFF_FD",
        "sample_sha256": put(fds / "samples.jsonl", {"fake": True}),
        "pack": evidence,
        "samples": 4,
    }
    side_sha = put(fds / "receipt.json", proof)
    old_status = {"status": "FAIL_PRESERVED", "model_launch_receipts": 1, "reason": why}
    old_sha = put(
        old / "receipt.json",
        old_status
        | {
            "build_receipt_sha256": "build",
            "unexecuted_arms": ["overlay_off", "overlay_on"],
            "arms": {
                "control_off": {
                    "receipt_sha256": put(
                        old / "control_off/receipt.json", old_status | {"unit": unit}
                    )
                }
            },
        },
    )
    libraries = {"original": ac.p.live.static.C291, "control": "ctrl", "overlay": "ov"}
    tree = {"files": 3266, "total_bytes": 88704231, "sha256_name_size_content_v1": ac.C292_TREE}
    arms, reviewed = {}, {}
    for i, name in enumerate(("control_off", "overlay_off", "overlay_on")):
        dest = new / name
        ident = {"pid": 41 + i, "start_ticks": 1240 + i}
        if i:
            unit = name
            raw = dest / "raw"
        digest = libraries["control" if not i else "overlay"]
        arm = {
            "mode": name,
            "unit": unit,
            "status": "PASS_C292_ARM_NUMERICS",
            "journal_enabled": i == 2,
            "image_sha256": digest,
            "capture_tree": tree,
            "cleanup": True,
            "model_launch_receipts": int(i != 0),
            "monitor_sha256": put(
                raw / (unit + ".json"),
                {"returncode": 0, "stop_reason": None, "process_identity": ident},
            ),
            "launch_sha256": put(raw / (unit + ".launch.json"), {"process_identity": ident}),
            "loader": {
                "native_pid": ident["pid"],
                "loader_sha256": put(raw / f"loader.{ident['pid']}", {"native_pid": ident["pid"]}),
            },
            "numerical_sha256": put(dest / "numerical.json", {"fixture": True}),
            "c127_sha256": put(dest / "selected.json", {"fixture": True}),
        }
        if not i:
            arm.update(
                pack=evidence,
                reused_measured_control=True,
                scoped_wall_s=None,
                r01_family_sha256=old_sha,
                live_fd_sha256=side_sha,
            )
        public = {k: arm[k] for k in ("image_sha256", "capture_tree", "status", "journal_enabled")}
        arms[name] = public | {"receipt_sha256": put(dest / "receipt.json", arm)}
        reviewed[name] = {
            "image_sha256": digest,
            "processes": 1,
            "startup_count": 18,
            "capture_tree": tree,
            "numerical_sha256": arm["numerical_sha256"],
        }
    row = {
        "status": "PASS_C292_PACK_OBSERVER_NUMERIC",
        "model_launch_receipts": 2,
        "revalidated_prior_launch_receipts": 1,
        "unexecuted_arms": [],
        "arms": arms,
        "libraries": libraries,
        "build_receipt_sha256": "build",
    }
    a.bridge_sha256 = put(new / "receipt.json", row)
    a.bridge_review_sha256 = put(
        a.bridge_review,
        {
            "status": "REPRODUCED_C292_PACK_OBSERVER_NUMERIC",
            "family_sha256": a.bridge_sha256,
            "failed_family_sha256": old_sha,
            "live_control_sha256": side_sha,
            "build_sha256": "build",
            "model_launches_by_reviewer": 0,
            "gold_receipt_sha256": ac.p.capture.C270,
            "original_family_sha256": ac.p.screen.C292,
            "arms": reviewed,
        },
    )
    return a, old_sha, side_sha


class Reopen(unittest.TestCase):
    def test_sources_follow_the_physical_process(self):
        faults = (None, "second_control", "sidecar", "old_monitor", "new_grade", "other_review")
        for fault in faults:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                a, old_sha, side_sha = example(Path(tmp))
                if fault == "second_control":
                    put(a.bridge_dir / "control_off/raw/repeated.launch.json", {})
                if fault == "sidecar":
                    put(a.bridge_fds_dir / "samples.jsonl", {})
                if fault == "old_monitor":
                    put(a.bridge_failed_dir / "control_off/raw/original-control.json", {})
                if fault == "new_grade":
                    put(a.bridge_dir / "overlay_on/selected.json", {})
                if fault == "other_review":
                    r = ac.read(a.bridge_review)
                    a.bridge_review_sha256 = put(a.bridge_review, r | {"family_sha256": "foreign"})
                b = {"candidate_sha256": "ov", "control_sha256": "ctrl"}
                with patch.multiple(ac, C292_FAILED=old_sha, C292_CONTROL_FDS=side_sha):
                    if fault:
                        with self.assertRaises(ValueError):
                            ac.bridge(a, b)
                    else:
                        self.assertEqual(ac.bridge(a, b)["model_launch_receipts"], 2)


if __name__ == "__main__":
    unittest.main()
