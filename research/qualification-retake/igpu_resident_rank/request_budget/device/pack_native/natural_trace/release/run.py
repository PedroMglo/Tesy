"""Reopen a completed, externally sealed C291/P family and price the ON arm offline."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NATURAL = run_path(str(HERE.parent / "analyse.py"))
RELEASE = run_path(str(HERE / "review.py"))
check = NATURAL["check"]


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def sealed(path, expected):
    raw = path.read_bytes()
    check(hashlib.sha256(raw).hexdigest() == expected, f"digest: {path.name}")
    return json.loads(raw)


def chain(root, family_hash):
    family = sealed(root / "family.json", family_hash)
    check(family["status"] == "COMPLETED_PACK_NATURAL_OBSERVATION", "terminal family")
    check(
        family["identity"]["journal_auditor_sha256"] == digest(HERE.parent / "analyse.py"),
        "natural auditor source",
    )
    on = root / "ON"
    member = family["arms"]["ON"]
    arm = sealed(on / "arm.json", member["sha256"])
    check(
        arm == member["arm"]
        and (arm["status"], arm["mode"]) == ("PASS_ONE_NATURAL_ARM", "ON")
        and arm["grade"]["status"] == "PASS_REVIEWED_TWO_NATURAL_TURNS"
        and arm["grade"]["receipt_sha256"] == arm["receipt_sha256"],
        "family/arm lineage",
    )
    receipt = sealed(on / "receipt.json", arm["receipt_sha256"])
    audit = sealed(on / "journal-audit.json", arm["journal_audit_sha256"])
    check(
        audit["status"] == arm["journal_status"] == family["journal_status"]
        and audit["status"] in ("PASS_PACK_NATURAL_TRACE", "INCOMPLETE_PACK_NATURAL_TRACE")
        and receipt["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and receipt["model_launches"] == 1
        and receipt["transport"]["mode"] == "P"
        and receipt["pack_events"]["label"] == "ON",
        "completed ON observation",
    )
    check(
        digest(on / "raw/events.pfj")
        == receipt["pack_events"]["journal_sha256"]
        == audit["header"]["journal_sha256"],
        "sealed PFJ",
    )
    return family, arm, receipt, audit


def reproduce(root, family_hash, result_hash=None, http_hash=None):
    family, arm, receipt, snapshot = chain(root, family_hash)
    on = root / "ON"
    src = on / "raw"
    keys = {}
    for name, expected in (("T2-result.json", result_hash), ("T2-request.jsonl", http_hash)):
        keys[name] = digest(src / name)
        check(expected is None or expected == keys[name], f"external digest: {name}")
    checked = NATURAL["audit_arm"](on, receipt, receipt["pack_events"]["before_second_ns"])
    # A JSON round trip normalizes tuples from the Python auditor to wire arrays.
    check(json.loads(json.dumps(checked)) == snapshot, "recomputed full natural audit")
    rows, header = NATURAL["PFJ"]["read_journal"](src / "events.pfj")
    check(header == snapshot["header"], "reopened PFJ")
    result = RELEASE["measure"](rows, NATURAL["host_trace"](rows), receipt["rows"][1])
    for name, expected in keys.items():
        check(digest(src / name) == expected, f"input changed: {name}")
    return {
        "status": result["status"],
        "release": result,
        "inputs_sha256": {
            "family.json": family_hash,
            "ON/arm.json": family["arms"]["ON"]["sha256"],
            "ON/receipt.json": arm["receipt_sha256"],
            "ON/journal-audit.json": arm["journal_audit_sha256"],
            "ON/raw/events.pfj": header["journal_sha256"],
            **{"ON/raw/" + name: value for name, value in keys.items()},
        },
        "producer_stderr_sha256": receipt["native_ids"]["stderr_sha256"],
        "external_http_raw_hashes_supplied": {
            "T2-result.json": result_hash is not None,
            "T2-request.jsonl": http_hash is not None,
        },
        "clock_transfer": family["paired"]["clock_transfer"],
        "jobs": checked["jobs"]["counts"],
        "route": checked["route"],
        "sources_sha256": {
            f: digest(p)
            for f, p in (
                ("run.py", HERE / "run.py"),
                ("review.py", HERE / "review.py"),
                ("protocol.md", HERE / "protocol.md"),
                ("natural_trace/analyse.py", HERE.parent / "analyse.py"),
                ("natural_trace/jobs.py", HERE.parent / "jobs.py"),
                ("natural_trace/client_cut.py", HERE.parent / "client_cut.py"),
            )
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family-dir", type=Path, required=True)
    parser.add_argument("--family-sha256", required=True)
    parser.add_argument("--t2-result-sha256")
    parser.add_argument("--t2-request-sha256")
    parser.add_argument("--new-output-dir", type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = reproduce(a.family_dir, a.family_sha256, a.t2_result_sha256, a.t2_request_sha256)
    except Exception as exc:
        # Exception values can include private JSON. Preserve a source location only.
        tb = exc.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        report = {
            "status": "FAIL_PRESERVED",
            "family_sha256": a.family_sha256,
            "error": type(exc).__name__,
            "location": [Path(tb.tb_frame.f_code.co_filename).name, tb.tb_lineno],
        }
    with (a.new_output_dir / "receipt.json").open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(report["status"])
    return int(report["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
