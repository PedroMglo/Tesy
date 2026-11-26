"""Prepare or supervise the BANK288 then BANK161 C110 family."""

import argparse
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
AUTH = run_path(str(HERE / "authority.py"))
OPS, S, CPU, DEVICE = (AUTH[k] for k in ("OPS", "S", "CPU", "DEVICE"))
need, sha, save = S["need"], S["sha"], DEVICE["save"]
MODES = ("BANK288", "BANK161")


def ready(mode, r):
    g = r["grade"]
    need(
        g["status"] == "PASS_IK_GPU_BANK_ARM"
        and (g["slots"], g["group_layers"], g["consumer_ops"], g["sites"], g["ordered_quartets"])
        == (int(mode.removeprefix("BANK")), 36, 432, 72, 597),
        "incomplete native bank grade",
    )
    need(
        r["model_starts"] == 1
        and r["returncode"] == r["swap_peak"] == 0
        and r["restored"]
        and r["child_gone"]
        and list(r["ack_elapsed_s"]) == list(OPS["PHASE"]),
        "arm cleanup or coverage",
    )
    for pos in (15, 16):
        row = r["rows_at_ack"][str(pos)]
        need(
            row["sha256"] == g["logits_sha256"][f"pos{pos}.f32"]
            and row["finite"]
            and row["max_ties"] == 1
            and row["top5"][0] == OPS["EXPECTED"][pos],
            "unqualified row",
        )


def inventory(out):
    need(S["raw_size"](out) <= OPS["CAP_RAW"], "raw budget")
    return {
        p.relative_to(out).as_posix(): sha(p)
        for p in sorted(out.rglob("*"))
        if p.is_file() and p != out / "receipt.json"
    }


def scope_end(a, arm):
    end, cg = CPU["scope_state"](a.unit, 10)
    CPU["own_scope"](cg)
    arm.update(cgroup_end=end, swap_peak=int((cg / "memory.swap.peak").read_text()))
    need(
        not any(end["events_local"][k] for k in ("oom", "oom_kill")) and arm["swap_peak"] == 0,
        "OOM or swap at termination",
    )


def available_rows(out):
    rows = {}
    for pos in (15, 16):
        path = out / "native" / f"pos{pos}.f32"
        if path.is_file() and not path.is_symlink():
            rows[str(pos)] = {"bytes": path.stat().st_size, "sha256": sha(path)}
            if path.stat().st_size == 804352:
                rows[str(pos)].update(OPS["written_row"](out / "native", pos))
    return rows


def one(a, folder, mode, state, authority, grader):
    profile, bound, w, policy, limits, expiry, refs, monitor = authority
    r = {
        "status": "FAIL_PRESERVED",
        "mode": mode,
        "model_starts": 0,
        "plan_sha256": profile["plan_sha256"],
    }
    try:
        native, stdout, stderr = OPS["arm"](
            mode, a, folder, r, bound, w, policy, limits, expiry, monitor
        )
        g = grader["check_arm"](mode, stdout.read_text(), stderr.read_text(), native, bound[3])
        r["grade"] = g
        scope_end(a, r)
        ready(mode, r)
        r["reference_contrasts"] = grader["against_references"](native, g, refs)
        r["status"] = g["status"]
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            scope_end(a, r)
            r["available_rows"] = available_rows(folder)
            r["raw_sha256"] = inventory(folder)
        except Exception as exc:
            r.update(status="FAIL_PRESERVED", inventory_or_scope_error=str(exc))
        save(folder / "receipt.json", r)
        state["arms"][mode] = dict(
            status=r["status"],
            receipt_sha256=sha(folder / "receipt.json"),
            model_starts=r["model_starts"],
            returncode=r.get("returncode"),
        )
        state["model_starts"] += r["model_starts"]
    need(
        r["status"] == "PASS_IK_GPU_BANK_ARM",
        mode + " " + r.get("reason", r.get("inventory_or_scope_error", "failed")),
    )
    return r


def sequence(a, out, state, authority, grader, execute=one):
    prior = None
    for mode in MODES:
        if mode == "BANK161":
            need(prior is not None and prior["status"] == "PASS_IK_GPU_BANK_ARM", "BANK288 gate")
            ready("BANK288", prior)
            need(
                sha(out / "BANK288/receipt.json") == state["arms"]["BANK288"]["receipt_sha256"],
                "BANK288 receipt changed",
            )
            need(
                all(sha(out / "BANK288" / p) == h for p, h in prior["raw_sha256"].items()),
                "BANK288 raw changed",
            )
        folder = out / mode
        folder.mkdir(mode=0o700)
        arm = execute(a, folder, mode, state, authority, grader)
        if prior is None:
            prior = arm
    state["pair"] = grader["check_pair"](
        out / "BANK288/native", prior["grade"], out / "BANK161/native", arm["grade"]
    )
    status = state["pair"]["status"]
    need(
        status
        in (
            "PASS_BANK_SIZE_PARITY_TWO_CUTS",
            "NO_GO_BANK_SIZE_PARITY",
            "INCONCLUSIVE_BANK_SIZE_PARITY",
            "INCONCLUSIVE_NO_PLACEMENT_OR_SERVICE_CONTRAST",
        ),
        "unknown pair terminal",
    )
    state["status"] = status


def run(a, out, state):
    authority = AUTH["prepare"](a)
    state.update(authority[0])
    if not a.execute:
        state["status"] = "PREPARED_ONLY"
        return
    state["prepared_sha256"] = a.prepared_sha256
    state["unit"] = a.unit
    grader = run_path(str(HERE.parent / "grade.py"))
    sequence(a, out, state, authority, grader)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "capacity",
        "capacity-client",
        "tiny",
        "tiny-review",
        "client",
        "dso",
        "inputs",
        "ids",
        "placement",
        "env49-map",
        "c55",
        "stock-file",
        "c110-parent",
        "cpu-d0",
        "cpu-d1",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    for key in (
        "commit",
        "capacity-sha256",
        "tiny-sha256",
        "tiny-review-sha256",
        "client-sha256",
        "inputs-sha256",
        "c55-sha256",
    ):
        p.add_argument("--" + key, required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--unit", default="")
    p.add_argument("--prepared", type=Path)
    p.add_argument("--prepared-sha256")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.absolute()
    out.mkdir(mode=0o700)
    state = dict(
        status="FAIL_PRESERVED",
        model_starts=0,
        model_start_limit=2,
        arms={m: {"status": "NOT_RUN", "model_starts": 0} for m in MODES},
        deadlines_s={"load": 180, "context": 90, "prefill": 90, "teacher": 90, "cleanup": 10},
        http_requests=0,
        raw_limit_B_per_arm=OPS["CAP_RAW"],
        namespace_read_stop_B_per_arm=1 << 40,
        energy_j=None,
    )
    try:
        run(a, out, state)
    except Exception as exc:
        state.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        save(out / "receipt.json", state)
    print(state["status"], state.get("reason", ""))
    return state["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
