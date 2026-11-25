"""Three qualified P processes with a static preflight and fail-closed predecessors."""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from runpy import run_path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profile as acquisition

HERE, p, OLD = acquisition.HERE, acquisition.p, acquisition.OLD
old = run_path(OLD / "family.py")
review = run_path(OLD / "review.py")
need, sha, save, pinned = p.need, p.sha, old["save"], p.pinned
MODES = acquisition.MODES
REF = (
    "repo",
    "placement",
    "window",
    "preflight_dir",
    "history_dir",
    "c270",
    "closure_dir",
    "derived_dir",
    "constructor_receipt",
    "c292_receipt",
    "build_dir",
    "fixture_dir",
)
SIG = (
    "commit",
    "unit_prefix",
    "preflight_sha256",
    "window_sha256",
    "c270_sha256",
    "build_sha256",
    "fixture_sha256",
)
PREPARED = "PREPARED_C291_PACK_OBSERVER"


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in (*REF, "new_output_dir"):
        parser.add_argument("--" + k.replace("_", "-"), type=Path, required=True)
    for k in SIG:
        parser.add_argument("--" + k.replace("_", "-"), required=True)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--prepared-sha256")
    parser.add_argument("--method", choices=("exact", "toolchain"), default="exact")
    parser.add_argument("--bridge-dir", type=Path)
    parser.add_argument("--bridge-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--arm", choices=MODES, help=argparse.SUPPRESS)
    return parser.parse_args()


def identity(a):
    need(
        a.repo.resolve(strict=True) == old["ROOT"]
        and old["version"]("rev-parse", "HEAD") == a.commit
        and not old["version"]("status", "--porcelain")
        and sha(HERE / "protocol.md") == acquisition.PROTOCOL,
        "clean frozen checkout",
    )
    need(re.fullmatch(r"tesy-c281-nvme-[a-z0-9-]+", a.unit_prefix), "unit prefix")
    need(
        a.preflight_sha256 == p.live.static.PREFLIGHT and a.c270_sha256 == p.capture.C270,
        "fixed preflight/C270",
    )
    fixture = a.fixture_dir / "receipt.json"
    build = a.build_dir / "receipt.json"
    b = pinned(build, a.build_sha256)
    labels = acquisition.order_for(b, a.method)
    need(
        pinned(fixture, a.fixture_sha256)["status"] == "PASS_PACK_NATIVE_FIXTURE_EXECUTIONS",
        "fixture gate",
    )
    if a.method == "toolchain":
        need(sha(HERE / "toolchain.md") == acquisition.ADDENDUM, "toolchain protocol")
        acquisition.bridge(a, b)
    else:
        need(a.bridge_dir is None and a.bridge_sha256 is None, "unexpected bridge")
    journal_auditor = HERE.parent / "natural_trace/analyse.py"
    order = p.conversation.window_order(a.window, a.window_sha256, fixture)
    need(order["start_unix_s"] >= build.stat().st_mtime, "C55 before production build")
    if a.bridge_dir:
        need(
            order["start_unix_s"] >= (a.bridge_dir / "receipt.json").stat().st_mtime,
            "C55 before numeric bridge",
        )
    return {
        "commit": a.commit,
        "tree": old["version"]("rev-parse", "HEAD^{tree}"),
        "args": {k: getattr(a, k) for k in SIG},
        "inputs": {k: str(getattr(a, k).resolve(strict=True)) for k in REF},
        "sources": {
            p.name: sha(p) for p in (HERE / "family.py", HERE / "profile.py", HERE / "protocol.md")
        },
        "journal_auditor_sha256": sha(journal_auditor),
        "method": a.method,
        "bridge_sha256": a.bridge_sha256,
        "toolchain_protocol_sha256": acquisition.ADDENDUM if a.method == "toolchain" else None,
        "bridge_dir": str(a.bridge_dir.resolve(strict=True)) if a.bridge_dir else None,
        "c55_order": order,
        "order": list(labels),
    }


def graded(out, result, a, label):
    current = result["transport"]["libllama"]["sha256"]
    expected = (
        p.live.static.C291
        if label == "BASE"
        else pinned(a.build_dir / "receipt.json", a.build_sha256)[
            "control_sha256" if label == "CONTROL" else "candidate_sha256"
        ]
    )
    need(
        current == expected
        and result["pack_events"]["label"] == label
        and result["transport"]["mode"] == "P",
        "review provider/pack",
    )
    if label == "BASE":
        return review["grade_arm"](out, result, a.history_dir)

    # Reuse every live-map, FD, owner, shutdown and client check. Supply the new
    # production provider only to the predecessor's branch selecting the P digest.
    def selected_module(path):
        need(
            path.resolve(strict=True)
            == (OLD.parents[1] / "capture_profile/screen.py").resolve(strict=True),
            "unexpected provider contract",
        )
        return {"C269": p.live.static.C269, "C291": expected}

    transport = acquisition.with_globals(review["transport_summary"], run_path=selected_module)
    return acquisition.with_globals(review["grade_arm"], transport_summary=transport)(
        out, result, a.history_dir
    )


def single(a, out):
    a.unit = a.unit_prefix + "-" + a.arm.lower()
    if not a.execute:
        return {
            "mode": a.arm,
            "status": "PREPARED_ONLY",
            "profile": acquisition.invoke(a, out, a.arm, False),
        }
    result = acquisition.invoke(a, out, a.arm, True)
    save(out / "receipt.json", result)
    summary = graded(out, result, a, a.arm)
    for row in summary["rows"]:
        row["server_ms_per_output"] = 1000 * row["decode_s"] / row["predicted_n"]
        row["native_evaluations_after_first"] = row["predicted_n"] - 1
        row["decode_ms_per_post_first_evaluation"] = (
            1000 * row["decode_s"] / (row["predicted_n"] - 1)
        )
    report = None
    if a.arm == "ON":
        check = run_path(HERE.parent / "natural_trace/analyse.py")["audit_arm"]
        report = check(out, result, result["pack_events"]["before_second_ns"])
        save(out / "journal-audit.json", report)
        need(
            report["status"] in {"PASS_PACK_NATURAL_TRACE", "INCOMPLETE_PACK_NATURAL_TRACE"},
            "journal status",
        )
    return {
        "status": "PASS_ONE_NATURAL_ARM",
        "mode": a.arm,
        "grade": summary,
        "receipt_sha256": sha(out / "receipt.json"),
        "journal_status": report["status"] if report else None,
        "journal_audit_sha256": sha(out / "journal-audit.json") if report else None,
    }


def compare(arms, labels):
    grades = [arms[name]["arm"]["grade"] for name in labels]
    need(
        all(g["trajectories"] == grades[0]["trajectories"] for g in grades),
        "unequal trajectories",
    )
    need(all(g["requests"] == 2 and g["model_launches"] == 1 for g in grades), "work")
    pairs = {}
    prices = [[r | {"valid_wall_s": r["transport_complete_s"]} for r in g["rows"]] for g in grades]
    for i in range(1, len(labels)):
        ratio = p.conversation.paired_cost(prices[i - 1], prices[i])["ON_over_OFF"]
        pairs[labels[i] + "_over_" + labels[i - 1]] = dict(zip(("T1", "T2"), ratio, strict=True))
    within = all(0.85 <= v <= 1.15 for pair in pairs.values() for v in pair["T2"].values())
    return {
        "ratios": pairs,
        "T2_all_in_band": within,
        "T2_ratios_checked": 4 * len(pairs),
        "clock_transfer": "WITHIN_SINGLE_BLOCK_BAND" if within else "INCONCLUSIVE_OUTSIDE_BAND",
        "population_neutrality": "UNIDENTIFIED",
        "runs_per_mode": 1,
    }


def family(a, out, current):
    labels = current["order"]
    prepared = None
    if a.execute:
        need(a.prepared and a.prepared_sha256, "pinned preflight required")
        prepared = pinned(a.prepared, a.prepared_sha256)
        need(
            prepared["status"] == PREPARED and prepared["identity"] == current, "preflight mismatch"
        )
        for mode in labels:
            need(
                sha(a.prepared.parent / mode / "arm.json") == prepared["arms"][mode]["sha256"],
                "prepared arm",
            )
    else:
        need(a.prepared is None and a.prepared_sha256 is None, "unexpected preflight")
    arms, waits = {}, {}
    start = time.monotonic()
    child = acquisition.with_globals(old["call_child"], HERE=HERE)
    for i, mode in enumerate(labels):
        if a.execute and i:
            waits[mode] = old["await_closed_endpoint"](out, a.unit_prefix, labels[i - 1])
        remaining = 650 * len(labels) - (time.monotonic() - start)
        need(remaining > 0, "family deadline")
        arms[mode] = child(a, out, mode, min(remaining, 650))
        need(
            sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
            <= (64 << 20) * len(labels),
            "family raw cap",
        )
    analysis = compare(arms, labels) if a.execute else None
    return {
        "status": "COMPLETED_PACK_NATURAL_OBSERVATION" if a.execute else PREPARED,
        "identity": current,
        "arms": arms,
        "paired": analysis,
        "journal_status": arms["ON"]["arm"].get("journal_status"),
        "prepared_sha256": a.prepared_sha256,
        "closed_endpoint_wait_s": waits,
        "model_launches": len(labels) if a.execute else 0,
        "requests": 2 * len(labels) if a.execute else 0,
        "elapsed_s": time.monotonic() - start,
    }


def main():
    a = arguments()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        current = identity(a)
        labels = current["order"]
        need(a.arm is None or a.arm in labels, "unregistered arm")
        if a.arm and a.execute:
            # A child may not bypass the prepared block or the immediately preceding arm.
            need(a.prepared and a.prepared_sha256, "child preflight required")
            prepared = pinned(a.prepared, a.prepared_sha256)
            need(
                prepared["status"] == PREPARED
                and prepared["identity"] == current
                and sha(a.prepared.parent / a.arm / "arm.json")
                == prepared["arms"][a.arm]["sha256"],
                "child preflight",
            )
            need(out.name == a.arm, "child destination")
            if a.arm != labels[0]:
                prev = labels[labels.index(a.arm) - 1]
                prior = out.parent / prev
                r = p.conversation.read(prior / "arm.json")
                need(
                    r["status"] == "PASS_ONE_NATURAL_ARM"
                    and r["mode"] == prev
                    and sha(prior / "receipt.json") == r["receipt_sha256"]
                    and (out.parent / (prev + "-closed-endpoint.json")).is_file(),
                    "previous arm",
                )
        result = single(a, out) if a.arm else family(a, out, current)
    except Exception as err:
        result = {
            "status": "FAIL_PRESERVED",
            "reason": f"{type(err).__name__}: {err}",
            "mode": a.arm,
            "model_launch_receipts": len(list(out.rglob("*.launch.json"))),
            "completed_arm_files": {
                k: sha(out / k / "arm.json") for k in MODES if (out / k / "arm.json").is_file()
            },
        }
    save(out / ("arm.json" if a.arm else "family.json"), result)
    print(result["status"], result.get("reason", ""), flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
