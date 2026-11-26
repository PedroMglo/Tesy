"""Run one 120B capacity process or the contemporary ON/OFF two-bank C110 family."""

import argparse
import fcntl
import os
from contextlib import ExitStack
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(str(HERE / "real_authority.py"))
CAP, FR, OFF, G, need, sha = (A[k] for k in ("CAP", "FR", "OFF", "G", "need", "sha"))
save = FR["save"]
ORDER = (("ON", "BANK288"), ("OFF", "BANK288"), ("ON", "BANK161"), ("OFF", "BANK161"))


def complete(r):
    need(
        r["model_starts"] == 1
        and r["child_gone"]
        and r["restored"]
        and r["returncode"] == 0
        and r["swap_peak"] == 0,
        "native completion",
    )


def close_arm(a, out, r):
    FR["scope_end"](a, r)
    r["raw_sha256"] = FR["inventory"](out)


def numeric(a, out, mode, selection, authority, ongrade):
    profile, bound, w, policy, limits, expiry, monitor, historical, refs = authority
    exe, model, identity, plan, build, env, providers, paths, drivers = bound
    b = (
        exe,
        model,
        identity,
        plan,
        build,
        env | {"TESY_C110_CALLBACK": selection},
        providers,
        paths,
        drivers,
    )
    r = dict(
        status="FAIL_PRESERVED",
        mode=mode,
        selection=selection,
        plan_sha256=profile["plan_sha256"],
        model_starts=0,
    )
    try:
        native, stdout, stderr = FR["OPS"]["arm"](
            mode, a, out, r, b, w, policy, limits, expiry, monitor
        )
        FR["scope_end"](a, r)
        complete(r)
        if selection == "ON":
            output = stdout.read_text()
            need(
                [x for x in output.splitlines() if x.startswith("CB_EVAL ")] == ["CB_EVAL ON"],
                "callback ON marker",
            )
            g = G["check_arm"](mode, output, stderr.read_text(), native, plan)
            r["grade"] = g
            FR["ready"](mode, r)
            r["references"] = G["against_references"](native, g, refs)
            old = G["rows_from_grade"](a.historical / mode / "native", historical[mode])
            r["historical_rows"] = OFF["compare_rows"](native, old)
            r["historical_routes_equal"] = [x["logical"] for x in historical[mode]["ledger"]] == [
                x["logical"] for x in g["ledger"]
            ]
            r["status"] = g["status"]
        else:
            g = OFF["grade"](mode, out, plan, out.parents[1] / "ON", ongrade)
            r.update(grade=g, status=g["status"])
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            close_arm(a, out, r)
            r["available_rows"] = FR["available_rows"](out)
            source_folder = (
                out.parents[1] / "ON" / mode / "native"
                if selection == "OFF"
                else a.historical / mode / "native"
            )
            source_grade = ongrade if selection == "OFF" else historical[mode]
            ref = G["rows_from_grade"](source_folder, source_grade)
            kept = {
                p: v
                for p, v in ref.items()
                if r["available_rows"].get(str(p), {}).get("bytes") == 804352
            }
            r["available_contrasts"] = OFF["compare_rows"](out / "native", kept)
        except Exception as exc:
            r.update(status="FAIL_PRESERVED", final_error=str(exc))
        save(out / "receipt.json", r)
    return r


def run(a, out, state):
    au = A["prepare"](a)
    profile, b, w, policy, limits, end, monitor, _, _ = au
    state["authority"] = profile
    if not a.execute:
        state["status"] = "PREPARED_ONLY"
        return
    state.update(prepared_sha256=a.prepared_sha256, unit=a.unit, plan_sha256=profile["plan_sha256"])
    if a.stage == "capacity":
        CAP["arm"](a, out, state, b, w, policy, limits, end, monitor)
        FR["scope_end"](a, state)
        complete(state)
        state["grade"] = A["capacity_grade"](out, b[3])
        A["require_capacity"](state["grade"])
        state["status"] = "PASS_SYSTEM_CAPACITY_ZERO_FORWARD"
        return
    grades = {}
    for selection, mode in ORDER:
        for label, prior in state["arms"].items():
            directory = out / label
            need(sha(directory / "receipt.json") == prior["receipt_sha256"], "earlier arm changed")
            need(FR["inventory"](directory) == prior["raw_sha256"], "earlier raw changed")
        directory = out / selection / mode
        directory.parent.mkdir(exist_ok=True)
        directory.mkdir()
        r = numeric(a, directory, mode, selection, au, grades.get(mode))
        state["model_starts"] += r["model_starts"]
        state["arms"][selection + "/" + mode] = dict(
            status=r["status"],
            receipt_sha256=sha(directory / "receipt.json"),
            raw_sha256=r.get("raw_sha256", {}),
        )
        expected = "PASS_IK_GPU_BANK_ARM" if selection == "ON" else "PASS_CALLBACK_OFF_TWO_CUTS"
        if r["status"] != expected:
            state.update(
                status=r["status"],
                stop_arm=selection + "/" + mode,
                reason=r.get("reason", r.get("final_error", r["status"])),
            )
            return
        if selection == "ON":
            grades[mode] = r["grade"]
            if mode == "BANK161":
                pair = G["check_pair"](
                    out / "ON/BANK288/native",
                    grades["BANK288"],
                    out / "ON/BANK161/native",
                    grades["BANK161"],
                )
                state["between_on"] = pair
                if pair["status"] != "PASS_BANK_SIZE_PARITY_TWO_CUTS":
                    state.update(status=pair["status"], stop_arm="ON/BANK161")
                    return
    ref = {p: (out / "OFF/BANK288/native" / f"pos{p}.f32").read_bytes() for p in (15, 16)}
    state["between_off"] = OFF["compare_rows"](out / "OFF/BANK161/native", ref)
    state["status"] = OFF["decision"](state["between_off"], True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=("capacity", "parity"), required=True)
    for key in ("tiny", "client", "dso", "inputs", "placement", "ids", "c55", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    for key in (
        "capacity",
        "historical",
        "cpu-d0",
        "cpu-d1",
        "stock-file",
        "c110-parent",
        "prepared",
    ):
        p.add_argument("--" + key, type=Path)
    for key in ("tiny-sha256", "client-sha256", "c55-sha256", "commit"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--capacity-sha256")
    p.add_argument("--prepared-sha256")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--unit", default="")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.absolute()
    out.mkdir(mode=0o700)
    state = dict(
        status="FAIL_PRESERVED",
        model_starts=0,
        model_start_limit=1 if a.stage == "capacity" else 4,
        http_requests=0,
        energy_j=None,
        arms={},
    )
    try:
        with ExitStack() as stack:
            if a.execute:
                lock = stack.enter_context(
                    (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a")
                )
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, state)
    except Exception as exc:
        state.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        if a.execute:
            try:
                FR["scope_end"](a, state)
                if a.stage == "capacity":
                    state["raw_sha256"] = FR["inventory"](out)
            except Exception as exc:
                state.update(status="FAIL_PRESERVED", final_error=str(exc))
        save(out / "receipt.json", state)
    print(state["status"], state.get("reason", ""), state.get("final_error", ""))
    return not (state["status"].startswith("PASS") or state["status"] == "PREPARED_ONLY")


if __name__ == "__main__":
    raise SystemExit(main())
