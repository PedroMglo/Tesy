"""Recheck two closed C281 arms and publish only aggregates and content digests."""

import argparse
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("closed_pfj_conversation", HERE / "profile.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
ARMS = {
    "OFF": "171e90939e42a55ce51b196224ecc2bb008cc7408205eae7e961d09759cdfc5f",
    "ON": "78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43",
}
SELECTED_METRICS = (
    "input_n",
    "cache_n",
    "prompt_n",
    "completion_n",
    "predicted_n",
    "completion",
    "functional",
    "prefix",
    *P.METRICS,
    "decode_tok_s",
)


def arm_summary(directory, expected, history):
    hashed = ARMS[expected]
    r = P.pinned(directory / "receipt.json", hashed)
    P.need(
        r["status"] == "PASS_C281_PFJ_" + expected
        and r["mode"] == expected
        and r["model_launches"] == 1
        and r["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
        "incorrect arm outcome",
    )
    unit = r["unit"]
    P.need(unit == Path(unit).name, "unit name")
    raw = directory / "raw"
    launch = P.read(raw / (unit + ".launch.json"))
    mon = P.pinned(raw / (unit + ".json"), r["monitor_sha256"])
    P.need(
        mon["process_identity"] == launch["process_identity"]
        and mon["returncode"] == 0
        and mon["stop_reason"] == "INTERRUPTED_BY_OWNER",
        "monitor or termination",
    )
    P.need(
        P.sha(raw / (unit + ".start-inventory.jsonl")) == r["start_inventory"]
        and P.trajectories(raw, r, history) == r["trajectories"],
        "C118 or stream changed",
    )
    return r, {
        "raw_receipt_sha256": hashed,
        "status": r["status"],
        "cleanup": r["cleanup"],
        "monitor_sha256": r["monitor_sha256"],
        "interval_s": r["envelope_s"],
        "readiness_s": r["ready_s"],
        "native_monitor_elapsed_s": mon["elapsed_s"],
        "start_inventory_sha256": r["start_inventory"],
        "raw_bytes": P.capture.final_raw_bytes(raw),
        "maxima": r["maxima"],
        "trajectories": r["trajectories"],
        "model_launches": 1,
        "turns": [{k: t[k] for k in SELECTED_METRICS} for t in r["rows"]],
    }


def compact(a):
    P.need(P.samples.historic_manifest(a.historical), "historical identity")
    off, s0 = arm_summary(a.off_dir, "OFF", a.historical)
    on, s1 = arm_summary(a.on_dir, "ON", a.historical)
    P.need(
        off["gates"] == on["gates"]
        and off["trajectories"] == on["trajectories"]
        and P.paired_cost(off["rows"], on["rows"]) == on["paired_cost"],
        "pair compatibility",
    )
    analyzer = P.imported("closed_pfj_audit", P.INT / "analyse.py")
    journal = a.on_dir / "raw/events.pfj"
    data, header = analyzer.read_journal(journal)
    report = analyzer.audit(data, header, a.model)
    authoritative = P.pinned(a.on_dir / "journal-audit.json", on["journal_audit_sha256"])
    P.need(
        report == authoritative
        and report["status"] == "PASS"
        and report["fd_identity_checked"] is True
        and report["journal_sha256"] == on["journal_sha256"],
        "replayed PFJ1",
    )
    price = P.prompt_budget(on["rows"][1], report["nominal_prefill"])
    P.need(price == on["own_ON_price"], "same-request budgets")
    by_tier = collections.defaultdict(
        lambda: {
            "published": 0,
            "read_syscalls": 0,
            "requested": 0,
            "returned": 0,
            "set_payload": 0,
        }
    )
    for r in data:
        kind = analyzer.NAMES[r.kind]
        if kind not in ("PUBLISH", "READ", "SET"):
            continue
        P.need(0 <= r.layer < 36 and 1 <= r.call <= 48, "unattributed event")
        phase = "call5" if r.call == 1 else "call148" if r.call == 2 else "decode46"
        tier = "CPU" if r.layer < 25 else "CUDA0"
        row = by_tier[(phase, tier)]
        if kind == "READ":
            row["read_syscalls"] += 1
            row["requested"] += r.b
            row["returned"] += r.c
        elif kind == "SET":
            row["set_payload"] += r.a
        else:
            row["published"] += 1
    P.need(
        sum(r["returned"] for r in by_tier.values()) == report["returned"]
        and sum(r["published"] for r in by_tier.values()) == report["event_counts"]["PUBLISH"],
        "tier sum",
    )
    failures = {}
    for label, path, digest, status in (
        (
            "window_r1",
            a.c55_r1,
            "d6684a7c180bff3234f4e13a542cf3a83be04e3366c44951af18f206b12fbadb",
            "NOT_ADMITTED",
        ),
        (
            "window_r2",
            a.c55_r2,
            "402c8061afc0b259daa3c6d018ab56554ce942744cdcd547aeddc2b8fd44f0e3",
            "FAIL_INVENTORY",
        ),
        (
            "on_r1",
            a.on_r1,
            "8647c999c10448279d27a32db57b95d635ccdfac1f0f8f0f086907447a1b4fd5",
            "FAIL_PRESERVED",
        ),
    ):
        f = P.pinned(path / "receipt.json", digest)
        P.need(f["status"] == status and not f.get("model_launches", 0), "historical FAIL")
        failures[label] = {
            "raw_receipt_sha256": digest,
            "status": status,
            "model_launches": 0,
            "cause": f.get("reason") or f.get("error") or f["failure"],
        }
    P.need(P.sha(a.c55_r3 / "receipt.json") == off["gates"]["c55_sha256"], "window R03")
    pre = P.read(a.precheck / "receipt.json")
    P.need(
        pre["status"] == "PREPARED_ONLY"
        and pre["gates"] == off["gates"]
        and pre["model_launches"] == 0,
        "preparation",
    )
    current = {k: v for k, v in report.items() if k != "calls"}
    current["by_phase_and_tier"] = {f"{p}/{t}": r for (p, t), r in by_tier.items()}
    current["calls"] = [
        {k: v for k, v in row.items() if k not in ("start_ns", "end_ns")}
        | {"duration_ns": row["end_ns"] - row["start_ns"]}
        for row in report["calls"]
    ]
    return {
        "status": "REPRODUCED_C281_PFJ_CONSERVATION",
        "physical_commit": off["gates"]["measurement_commit"],
        "physical_profile_sha256": off["profile_sha256"],
        "physical_protocol_sha256": off["protocol_sha256"],
        "addendum_sha256": off["denominator_addendum_sha256"],
        "shared_gates": off["gates"],
        "prior_attempts": failures,
        "precheck_sha256": P.sha(a.precheck / "receipt.json"),
        "OFF": s0,
        "ON": s1,
        "paired_cost": on["paired_cost"],
        "clock_transfer": on["clock_transfer"],
        "conditional_ON": price,
        "raw_journal_bytes": journal.stat().st_size,
        "raw_audit_sha256": on["journal_audit_sha256"],
        "journal": current,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "historical",
        "off-dir",
        "on-dir",
        "on-r1",
        "c55-r1",
        "c55-r2",
        "c55-r3",
        "precheck",
        "model",
        "new-output-dir",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        r = compact(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        r = {"status": "FAIL_PRESERVED", "error_type": type(error).__name__}
        (args.new_output_dir / "error.txt").write_text(str(error) + "\n")
    raw = (json.dumps(r, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    tmp = args.new_output_dir / "receipt.json.tmp"
    tmp.write_bytes(raw)
    os.replace(tmp, args.new_output_dir / "receipt.json")
    print(r["status"], hashlib.sha256(raw).hexdigest())
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
