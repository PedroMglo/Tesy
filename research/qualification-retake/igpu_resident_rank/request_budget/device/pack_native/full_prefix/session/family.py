"""Two new P processes, a private first-turn prefix seal and the historical OFF reference."""

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture as local

old, prior, base = local.prior["old"], local.prior, local.base
need, pinned, sha, save = local.need, local.pinned, local.sha, local.save
HERE = local.HERE
MODES = ("OFF", "ON")
PREPARED = "PREPARED_FULL_PREFIX_P_PAIR"
REF = (*prior["REF"], "bridge_dir", "prior_family")
SIG = (*prior["SIG"], "bridge_sha256")
AUX = 4 << 20
RAW = 64 << 20


def arguments():
    ap = argparse.ArgumentParser(description=__doc__)
    for k in (*REF, "new_output_dir"):
        ap.add_argument("--" + k.replace("_", "-"), type=Path, required=True)
    for k in SIG:
        ap.add_argument("--" + k.replace("_", "-"), required=True)
    ap.add_argument("--prepared", type=Path)
    ap.add_argument("--prepared-sha256")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--arm", choices=MODES, help=argparse.SUPPRESS)
    a = ap.parse_args()
    return a


def historical(a):
    row = pinned(a.prior_family / "family.json", local.OLD_FAMILY)
    need(
        row["status"] == "COMPLETED_PACK_NATURAL_OBSERVATION"
        and row["journal_status"] == "PASS_PACK_NATURAL_TRACE"
        and list(row["identity"]["order"]) == ["BASE", "CONTROL", "OFF", "ON"],
        "part-97 family",
    )
    ref = row["arms"]["OFF"]
    anchor = pinned(a.prior_family / "OFF/arm.json", ref["sha256"])
    need(anchor == ref["arm"], "part-97 OFF arm")
    evidence = pinned(a.prior_family / "OFF/receipt.json", anchor["receipt_sha256"])
    need(
        evidence["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
        and anchor["grade"]["requests"] == 2
        and [v["completion_n"] for v in anchor["grade"]["trajectories"]] == [78, 47],
        "part-97 reference workload",
    )
    return anchor


def identity(a):
    need(
        a.repo.resolve(strict=True) == old["ROOT"]
        and old["version"]("rev-parse", "HEAD") == a.commit
        and not old["version"]("status", "--porcelain")
        and sha(HERE / "protocol.md") == local.PROTOCOL,
        "clean frozen checkout",
    )
    need(re.fullmatch(r"tesy-c281-nvme-[a-z0-9-]+", a.unit_prefix), "unit prefix")
    need(
        a.preflight_sha256 == local.p.live.static.PREFLIGHT
        and a.c270_sha256 == local.p.capture.C270,
        "E20 authority",
    )
    h = historical(a)
    build = local.admission(a)
    order = local.p.conversation.window_order(
        a.window, a.window_sha256, a.fixture_dir / "receipt.json"
    )
    need(
        order["start_unix_s"]
        >= max((folder / "receipt.json").stat().st_mtime for folder in (a.bridge_dir, a.build_dir)),
        "C55 before physical qualifications",
    )
    files = (
        HERE / "protocol.md",
        HERE / "capture.py",
        HERE / "family.py",
        local.FULL / "protocol.md",
        local.FULL / "audit.py",
        local.FULL / "build.py",
        local.FULL / "numeric/bridge.py",
        local.POLICY_FILE,
        local.PACK / "conversation/profile.py",
        local.PACK / "conversation/family.py",
    )
    return {
        "commit": a.commit,
        "tree": old["version"]("rev-parse", "HEAD^{tree}"),
        "order": list(MODES),
        "args": {k: getattr(a, k) for k in SIG},
        "inputs": {k: str(getattr(a, k).resolve(strict=True)) for k in REF},
        "candidate_sha256": build["candidate_sha256"],
        "historical_off_receipt_sha256": h["receipt_sha256"],
        "historical_family_sha256": local.OLD_FAMILY,
        "c55_order": order,
        "source_sha256": {str(f.relative_to(a.repo)): sha(f) for f in files},
    }


def single(a, out):
    a.unit = a.unit_prefix + "-" + a.arm.lower()
    result = local.invoke(a, out, a.arm, a.execute)
    if not a.execute:
        return {"status": "PREPARED_ONLY", "mode": a.arm, "profile": result}
    result["pack_events"] = {"label": a.arm}
    save(out / "receipt.json", result)
    # Retain every previous workload, PID, data-FD, cleanup, cgroup and token assertion.
    # The preceding grader expects its label in pack_events; the raw remains immutable.
    grade = prior["graded"](out, result, a, a.arm)
    h = historical(a)
    need(
        grade["trajectories"] == h["grade"]["trajectories"]
        and grade["requests"] == 2
        and grade["model_launches"] == 1,
        "historical OFF full trajectories",
    )
    for row in grade["rows"]:
        row["server_ms_per_output"] = 1000 * row["decode_s"] / row["predicted_n"]
        row["native_evaluations_after_first"] = row["predicted_n"] - 1
        row["decode_ms_per_post_first_evaluation"] = (
            1000 * row["decode_s"] / (row["predicted_n"] - 1)
        )
    r = result["full_prefix"]
    return {
        "status": "PASS_ONE_NATURAL_ARM",
        "mode": a.arm,
        "grade": grade,
        "receipt_sha256": sha(out / "receipt.json"),
        "journal_status": "PASS_FULL_PREFIX_NATURAL_JOURNAL" if a.arm == "ON" else None,
        "journal_audit_sha256": r.get("journal_audit_sha256"),
        "before_t2_sha256": r.get("before_t2_sha256"),
        "t1_candidates_sha256": r.get("t1_candidates_sha256"),
    }


def family(a, out, current):
    if a.execute:
        need(a.prepared and a.prepared_sha256, "prepared gate")
        ready = pinned(a.prepared, a.prepared_sha256)
        need(
            ready["status"] == PREPARED
            and ready["identity"] == current
            and all(
                sha(a.prepared.parent / k / "arm.json") == ready["arms"][k]["sha256"] for k in MODES
            ),
            "preflight mismatch",
        )
    else:
        need(not a.prepared and not a.prepared_sha256, "unexpected preflight")
    start = time.monotonic()
    child = base.with_globals(old["call_child"], HERE=HERE)
    arms = {}
    waits = {}
    for mode in MODES:
        if a.execute and mode == "ON":
            waits[mode] = old["await_closed_endpoint"](out, a.unit_prefix, "OFF")
        remaining = 1300 - (time.monotonic() - start)
        need(remaining > 0, "family timeout")
        arms[mode] = child(a, out, mode, min(remaining, 650))
        folder = out / mode
        need(
            sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
            <= RAW + AUX + (local.BYTES if mode == "ON" else 0),
            "arm output limit",
        )
    need(sum(p.stat().st_size for p in out.iterdir() if p.is_file()) < AUX, "family overhead")
    paired = prior["compare"](arms, MODES) if a.execute else None
    return {
        "status": "PASS_C281_FULL_PREFIX_NATURAL_PAIR" if a.execute else PREPARED,
        "identity": current,
        "arms": arms,
        "paired": paired,
        "prepared_sha256": a.prepared_sha256,
        "model_launches": 2 if a.execute else 0,
        "requests": 4 if a.execute else 0,
        "closed_endpoint_wait_s": waits,
        "elapsed_s": time.monotonic() - start,
    }


if __name__ == "__main__":
    raise SystemExit(
        base.with_globals(
            prior["main"],
            arguments=arguments,
            identity=identity,
            single=single,
            family=family,
            MODES=MODES,
            PREPARED=PREPARED,
        )()
    )
