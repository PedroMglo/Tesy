"""Guard the two OFF processes on the original qualified driver and bank family."""

import argparse
import fcntl
import json
import os
import subprocess
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OFF = run_path(str(HERE / "grade.py"))
R, G, need = OFF["R"], OFF["G"], OFF["need"]
RUN = R["RUN"]
AUTH, OPS, CPU, DEVICE = (RUN[k] for k in ("AUTH", "OPS", "CPU", "DEVICE"))
sha, save, receipt = RUN["sha"], RUN["save"], AUTH["receipt"]
CALLBACK_ELF = "90efe5e2c39b0da9a47f656670f3f041941f376a1c5bd251a6ef1178faf59c3c"


def new_authority(a):
    need(a.c55.parent.name.startswith("tesy-ik-full-parity-c55-off-"), "dedicated OFF C55")
    if a.execute:
        need(a.unit.startswith("tesy-ik-e10-full-parity-off-"), "dedicated OFF scope")
    profile, bound, w, policy, limits, expiry, _, monitor = AUTH["prepare"](a)
    first = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    freeze = int(
        subprocess.check_output(
            ["git", "-C", HERE, "log", "-1", "--format=%ct", "--", "protocol.md"], text=True
        )
    )
    need(datetime.fromisoformat(first).timestamp() >= freeze, "C55 predates callback protocol")
    base_exe, model, identity, plan, old, env, providers, paths, drivers = bound
    b = receipt(a.callback_build / "receipt.json", a.callback_build_sha256)
    exe = a.callback_build / b["binary"]
    need(
        b["status"] == "PASS_CALLBACK_CLIENT_BUILD"
        and b["original_receipt_sha256"] == a.client_sha256
        and sha(base_exe) == b["control_elf_sha256"]
        and sha(exe) == b["binary_sha256"] == CALLBACK_ELF
        and b["build_script_sha256"] == sha(HERE / "build.py")
        and b["protocol_sha256"] == sha(HERE / "protocol.md")
        and b["source_sha256"] == sha(a.callback_build / "parity.cpp")
        and b["closure"] == old["closure"]
        and b["libraries"] == old["libraries"],
        "callback build",
    )
    need(
        profile["monitor_provider"]["kernel_driver"] == w["gpu_driver"] == "620.70.06",
        "changed driver requires tiny, capacity and contemporary ON controls",
    )
    regs = dict(providers)
    regs[str(exe)] = {"sha256": b["binary_sha256"], "stat": DEVICE["IO"].stat_id(exe)}
    child_env = env | {"TESY_C110_CALLBACK": "OFF"}
    CPU["loader"](exe, b, child_env)
    on = OFF["reference"](a.on_family, plan)
    extra = dict(
        build_sha256=a.callback_build_sha256,
        child_env=child_env,
        executable=regs[str(exe)],
        on_family_sha256=R["ROOT_SHA"],
        variants=["OFF288", "OFF161"],
        sources={p.name: sha(p) for p in (*HERE.glob("*.py"), HERE / "protocol.md")},
        original_pair_review_sha256=sha(HERE.parent / "review.py"),
    )
    if a.execute:
        prior = receipt(a.prepared / "receipt.json", a.prepared_sha256)
        need(prior.get("callback_authority") == extra, "callback authority changed")
    profile["callback_authority"] = extra
    bound = exe, model, identity, plan, b, child_env, regs, paths, drivers
    return profile, bound, w, policy, limits, expiry, on, monitor


def completion(arm):
    need(
        arm["model_starts"] == 1
        and arm["child_gone"]
        and arm["restored"]
        and arm["returncode"] == arm["swap_peak"] == 0
        and list(arm["ack_elapsed_s"]) == list(OPS["PHASE"]),
        "incomplete native process",
    )


def attempt(a, directory, mode, authority):
    profile, bound, w, policy, limits, expiry, on, monitor = authority
    r = dict(status="FAIL_PRESERVED", mode=mode, model_starts=0, plan_sha256=profile["plan_sha256"])
    try:
        OPS["arm"](mode, a, directory, r, bound, w, policy, limits, expiry, monitor)
        RUN["scope_end"](a, r)
        completion(r)
        grade = OFF["grade"](mode, directory, bound[3], a.on_family, on[mode])
        r.update(grade=grade, status=grade["status"])
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            RUN["scope_end"](a, r)
            r["available_rows"] = RUN["available_rows"](directory)
            r["raw_sha256"] = RUN["inventory"](directory)
            # A native greedy/nonfinite failure may precede its ACK. A preserved row
            # still gets compared, even when physical completion could not be proved.
            refs = G["rows_from_grade"](a.on_family / mode / "native", on[mode])
            preserved = {
                p: v
                for p, v in refs.items()
                if r["available_rows"].get(str(p), {}).get("bytes") == 804352
            }
            r["available_contrasts"] = OFF["compare_rows"](directory / "native", preserved)
        except Exception as exc:
            r.update(status="FAIL_PRESERVED", inventory_or_scope_error=str(exc))
        save(directory / "receipt.json", r)
    return r


def run(a, out, state):
    authority = new_authority(a)
    state.update(authority[0])
    if not a.execute:
        state["status"] = "PREPARED_ONLY"
        return
    state["prepared_sha256"] = a.prepared_sha256
    first = None
    for mode in RUN["MODES"]:
        if first is not None:
            p = out / "BANK288"
            need(
                sha(p / "receipt.json") == state["arms"]["BANK288"]["receipt_sha256"]
                and RUN["inventory"](p) == first["raw_sha256"],
                "first arm changed",
            )
        folder = out / mode
        folder.mkdir(mode=0o700)
        r = attempt(a, folder, mode, authority)
        state["arms"][mode] = dict(status=r["status"], receipt_sha256=sha(folder / "receipt.json"))
        state["model_starts"] += r["model_starts"]
        if r["status"] != "PASS_CALLBACK_OFF_TWO_CUTS":
            state.update(status=r["status"], stop_arm=mode, reason=r.get("reason", r["status"]))
            return
        if first is None:
            first = r
    a_rows = {p: (out / "BANK288/native" / f"pos{p}.f32").read_bytes() for p in (15, 16)}
    state["between_off"] = OFF["compare_rows"](out / "BANK161/native", a_rows)
    state["status"] = OFF["decision"](state["between_off"], True)


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
        "callback-build",
        "on-family",
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
        "callback-build-sha256",
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
        http_requests=0,
        arms={m: {"status": "NOT_RUN"} for m in RUN["MODES"]},
    )
    try:
        with ExitStack() as stack:
            if a.execute:
                lockdir = Path("/run/user") / str(os.getuid())
                lock = stack.enter_context((lockdir / "tesy-c110-callback.lock").open("a"))
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, state)
    except Exception as exc:
        state.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        save(out / "receipt.json", state)
    print(state["status"], state.get("reason", ""))
    return state["status"] in (
        "FAIL_PRESERVED",
        "NO_GO_CALLBACK_PARITY",
        "INCONCLUSIVE_SERVICE_CONTRAST",
    )


if __name__ == "__main__":
    raise SystemExit(main())
