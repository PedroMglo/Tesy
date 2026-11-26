"""Use the qualified physical C110 supervisor for original, DIRECT and selective inputs."""

import argparse
import fcntl
import json
import os
import time
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
C = run_path(str(HERE / "grade.py"))
A, FR, REAL, need = (C[k] for k in ("A", "FR", "REAL", "need"))
T = run_path(str(HERE.parent / "tiny_graph/review.py"))
B = run_path(str(HERE / "build.py"))
sha, receipt = A["sha"], A["receipt"]
SMALL = "d0973e97224a3136c168184c1715fe2e4e32acf664036a8a71728699fae6438d"


def freeze(a):
    prior_args = SimpleNamespace(
        **(vars(a) | dict(stage="parity", execute=False, prepared=None, prepared_sha256=None))
    )
    profile, bound, w, policy, limits, end, monitor, _old, refs = A["prepare"](prior_args)
    first = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        datetime.fromisoformat(first).timestamp()
        >= int(B["git"](HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "C55 predates input protocol",
    )
    tiny = T["review"](a.reader_tiny, SMALL, a.tiny, a.small_model)
    expected = json.loads((HERE.parent / "tiny_graph/result.json").read_bytes())
    need(json.loads(json.dumps(tiny)) == expected, "tiny numerical prerequisite")
    exe, model, identity, plan, old, env, providers, paths, drivers = bound
    build = receipt(a.build / "receipt.json", a.build_sha256)
    candidate = a.build / "c110-bank-input"
    need(
        build["status"] == "PASS_C110_INPUT_BUILD"
        and build["commit"] == a.commit
        and build["original_build"] == a.client_sha256 == B["HIST"]
        and sha(candidate) == build["binary_sha256"],
        "candidate/client identity",
    )
    ce, libs, driver = A["SYS"]["system_loader"](candidate, old, a.dso.resolve() / "objects")
    need(
        ce == env
        and set(libs) == paths
        and all(providers[k]["sha256"] == v for k, v in driver.items()),
        "candidate loader closure",
    )
    tracked = providers | {
        str(candidate): {
            "sha256": build["binary_sha256"],
            "stat": A["DEV"]["IO"].stat_id(candidate),
        }
    }
    on, schedules = C["history"](a.sys73, plan)
    state = dict(
        profile=profile,
        build_sha256=a.build_sha256,
        tiny_input_sha256=SMALL,
        previous_sha256=C["HISTORY"],
        providers=tracked,
        sources={
            p.name: sha(p) for p in (HERE / "protocol.md", HERE / "run.py", HERE / "grade.py")
        },
    )
    return (
        state,
        (exe, candidate, model, identity, plan, old, env, tracked, paths, drivers),
        (w, policy, limits, end, monitor),
        (on, schedules, refs),
    )


def run(a, out, r):
    state, bound, args, compare = freeze(a)
    r["authority"] = state
    if a.prepared is None:
        r["status"] = "PREPARED_ONLY"
        return
    prior = receipt(a.prepared / "receipt.json", a.prepared_sha256)
    need(prior["status"] == "PREPARED_ONLY" and prior["authority"] == state, "changed preflight")
    need(a.unit.startswith("tesy-ik-e10-input-"), "scope name")
    r["prepared_sha256"] = a.prepared_sha256
    exe, candidate, model, identity, plan, build, env, tracked, paths, drivers = bound
    deadline = time.monotonic() + 36 * 60
    for label, (source, selection) in C["SOURCES"].items():
        folder = out / label
        folder.mkdir(mode=0o700)
        arm = dict(
            status="FAIL_PRESERVED",
            model_starts=0,
            plan_sha256=state["profile"]["plan_sha256"],
            source=source,
            callback=selection,
        )
        try:
            local_env = env | {"TESY_C110_CALLBACK": selection}
            if source:
                local_env["TESY_C110_SOURCE"] = source
            ctx = (
                candidate if source else exe,
                model,
                identity,
                plan,
                build,
                local_env,
                tracked,
                paths,
                drivers,
            )
            FR["OPS"]["arm"](C["BANK"], a, folder, arm, ctx, *args)
            FR["scope_end"](a, arm)
            REAL["complete"](arm)
            grade = C["evaluate"](label, folder, a.sys73, model, plan, *compare)
            arm.update(grade)
            need(
                time.monotonic() < deadline
                and sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) < 256 << 20,
                "family budget",
            )
        except Exception as exc:
            arm.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
        finally:
            try:
                REAL["close_arm"](a, folder, arm)
                arm["available_rows"] = FR["available_rows"](folder)
            except Exception as exc:
                arm.update(status="FAIL_PRESERVED", final_error=str(exc))
            FR["save"](folder / "receipt.json", arm)
            r["model_starts"] += arm["model_starts"]
            r["arms"][label] = dict(
                status=arm["status"], receipt_sha256=sha(folder / "receipt.json")
            )
        if arm["status"] != "PASS_C110_BANK_INPUT_ARM":
            r.update(stop_arm=label, reason=arm.get("reason", arm.get("final_error")))
            return
    args[-1]()
    A["S"]["same_files"](tracked)
    r["status"] = "PASS_C110_BANK_INPUT_NUMERIC"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "client",
        "dso",
        "inputs",
        "placement",
        "ids",
        "tiny",
        "capacity",
        "historical",
        "c110-parent",
        "stock-file",
        "cpu-d0",
        "cpu-d1",
        "c55",
        "reader-tiny",
        "small-model",
        "sys73",
        "build",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in (
        "commit",
        "c55-sha256",
        "client-sha256",
        "tiny-sha256",
        "capacity-sha256",
        "build-sha256",
    ):
        p.add_argument("--" + k, required=True)
    p.add_argument("--prepared", type=Path)
    p.add_argument("--prepared-sha256")
    p.add_argument("--unit", default="")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", model_starts=0, http_requests=0, energy_j=None, arms={})
    try:
        need(bool(a.prepared) == bool(a.prepared_sha256) == bool(a.unit), "preflight or execute")
        if a.unit:
            with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open(
                "a"
            ) as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                run(a, out, r)
        else:
            run(a, out, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        if a.unit:
            try:
                FR["scope_end"](a, r)
            except Exception as exc:
                r.update(status="FAIL_PRESERVED", final_error=str(exc))
        FR["save"](out / "receipt.json", r)
    print(r["status"], r.get("stop_arm", ""), r.get("reason", ""), r.get("final_error", ""))
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
