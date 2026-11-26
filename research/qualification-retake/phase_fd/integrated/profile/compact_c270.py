"""Audit a terminal paired C270 family after relocating its private outputs."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from c270 import OLD, monitor_result, require_journal
from linkage import load_module, need, read, sha
from smoke import save

sys.path.insert(0, str(OLD))
import measure
from c210_witness_gate import qualified

AUDIT_R01 = "28c224bd734f841fb87a9e3b1350f0a1008308898d2629a396c7b21d2a56b443"


def compact(root, family_sha, reference, analyser):
    need(sha(root / "receipt.json") == family_sha, "family receipt")
    family = read(root / "receipt.json")
    need(
        family["status"] in {"FAIL_PRESERVED", "PASS_C270_PAIRED_NUMERIC_AND_JOURNAL"}
        and family["conversation"] == "NOT_RUN",
        "terminal numeric family",
    )
    old = load_module(OLD / "qualified_profile/compact.py", "stock_c270_compact")
    arms = []
    reference_data = None
    for i, item in enumerate(family["arms"]):
        mode = item["mode"]
        d = root / mode
        raw = d / "raw"
        r = read(d / "receipt.json")
        unit = r["unit"]
        need(
            mode == ("OFF", "ON")[i]
            and item["status"] == r["status"]
            and sha(d / "receipt.json") == item["receipt_sha256"],
            "arm binding",
        )
        row = dict(item)
        row["elapsed_arm_s"] = r["elapsed_arm_s"]
        if "error_type" in r:
            row["error_type"] = r["error_type"]
        hashed = {
            p.relative_to(raw).as_posix(): [p.stat().st_size, sha(p)]
            for p in raw.rglob("*")
            if p.is_file() and not p.is_symlink()
        }
        row.update(
            raw_file_count=len(hashed),
            raw_bytes=sum(z[0] for z in hashed.values()),
            raw_manifest_sha256=hashlib.sha256(
                json.dumps(hashed, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        need(row["raw_bytes"] == r["raw_bytes"], "raw length")
        ctrl_path = d / "phase-control.json"
        if ctrl_path.exists():
            need(sha(ctrl_path) == r["phase_control_sha256"], "arm authority")
            ctrl = read(ctrl_path)
            row["image_sha256"] = ctrl["image_sha256"]
        launch = raw / (unit + ".launch.json")
        need(
            int(launch.exists()) == r["model_launch_receipts"] == row["model_launch_receipts"],
            "launch count",
        )
        if "monitor_sha256" in r:
            mp = raw / (unit + ".json")
            schema = read(d / "resource-phase.json")
            need(
                sha(mp) == r["monitor_sha256"]
                and sha(launch) == r["launch_sha256"]
                and sha(d / "resource-phase.json") == ctrl["resource_sha256"],
                "scope monitor",
            )
            m = read(mp)
            pid = read(launch)["process_identity"]
            need(
                m["process_identity"] == pid
                and sha(raw / ("loader." + str(pid["pid"]))) == r["authority"]["loader_sha256"],
                "loader owner",
            )
            monitor_result(m, schema, ctrl["env"], measure)
            row["c118"] = old.validate_inventory(
                d, unit, {"native_explicit_env": ctrl["env"]}, read(launch)
            )
            row.update(
                maxima=m["maxima"],
                monitor_stop=m["stop_reason"],
                live_samples=r["live_samples"],
                elapsed_model_s=m["elapsed_s"],
                scoped_wall_s=r["scoped_wall_s"],
                monitor_sha256=sha(mp),
                launch_sha256=sha(launch),
                loader_sha256=r["authority"]["loader_sha256"],
            )
        if "selected_sha256" in r:
            numeric = read(d / "selected.json")
            need(sha(d / "selected.json") == r["selected_sha256"], "recorded numerical gate")
            measure.check_gate(numeric)
            if reference_data is None:
                reference_data = qualified(reference)
            observed = qualified(raw / (unit + ".capture"))
            need(
                all(observed[k] == reference_data[k] for k in ("core", "masks", "logits"))
                and numeric["prospective_witness"]
                == json.loads(json.dumps(observed["prospective_witness"])),
                "independent C127 replay",
            )
            row.update(selected_sha256=r["selected_sha256"], numerical_gate=numeric)
        if "journal_sha256" in r:
            journal = raw / "phase.pfj1"
            need(
                mode == "ON"
                and sha(journal) == r["journal_sha256"]
                and sha(d / "journal-audit.json") == r["journal_audit_sha256"],
                "sealed journal files",
            )
            records, head = analyser.read_journal(journal)
            stat = read(d / "resource-phase.json")["model_stat"]
            need(
                {(rec.a, rec.b) for rec in records if analyser.NAMES[rec.kind] == "FILE"}
                == {(stat["dev"], stat["inode"])},
                "original GGUF descriptor",
            )
            grade = analyser.audit(records, head)
            if grade["status"] == "PASS":
                # The physical audit obtained (dev,ino) by stat(model). The binding above
                # uses the original monitor's authenticated stat, including after relocation.
                need(grade["fd_identity_checked"] is False, "unexpected offline inode policy")
                grade["fd_identity_checked"] = True
            need(
                json.loads(json.dumps(grade, allow_nan=False)) == read(d / "journal-audit.json"),
                "offline conservation differs",
            )
            row.update(
                journal_sha256=r["journal_sha256"],
                journal_bytes=journal.stat().st_size,
                journal_audit_sha256=r["journal_audit_sha256"],
                records=head["records"],
                journal_status=grade["status"],
            )
            if grade["status"] == "PASS":
                require_journal(grade)
                row.update(
                    event_counts=grade["event_counts"],
                    calls=len(grade["calls"]),
                    fd_identity_witness="FILE(dev,ino)==recorded_monitor_model_stat",
                    service_totals={
                        k: grade[k]
                        for k in (
                            "requested",
                            "returned",
                            "payload",
                            "read_worker_ns",
                            "set_worker_ns",
                            "read_union_ns",
                            "set_union_ns",
                            "wait_union_ns",
                        )
                    },
                    by_origin={
                        name: {
                            k: sum(c[k] for c in calls)
                            for k in ("origin_loads", "origin_returned_bytes", "origin_payload")
                        }
                        for name, calls in (
                            ("prefill189", grade["calls"][:1]),
                            ("decode32", grade["calls"][1:]),
                        )
                    },
                )
            else:
                row["journal_failure_gate"] = grade["gate"]
        arms.append(row)
    need(
        sum(row["model_launch_receipts"] for row in arms) == family["model_launch_receipts"],
        "family launches",
    )
    return {
        **family,
        "arms": arms,
        "family_receipt_sha256": family_sha,
        "measurement_analyser_sha256": AUDIT_R01,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family-dir", "c127-reference", "analyser", "new-output"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    need(sha(a.analyser) == AUDIT_R01, "measurement parser identity")
    save(
        a.new_output,
        compact(
            a.family_dir,
            a.family_sha256,
            a.c127_reference,
            load_module(a.analyser, "qualify_phase_audit"),
        ),
    )
