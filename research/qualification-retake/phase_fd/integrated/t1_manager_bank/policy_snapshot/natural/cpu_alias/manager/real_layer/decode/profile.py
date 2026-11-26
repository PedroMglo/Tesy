"""Bounded supervisor for COPY, ALIAS and wrong-gate controls at the captured first CPU0 decode."""

import argparse
import hashlib
import json
import math
import os
import re
import signal
import struct
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = next(p for p in HERE.parents if p.name == "qualification-retake")
ROOT = QUAL.parents[1]
POLICY = QUAL / "packed_real_layer/policy/profile.py"
if (
    hashlib.sha256(POLICY.read_bytes()).hexdigest()
    != "8c991ac832da56c41d8934589039dfb683a09f060842998c4efb641a91013070"
):
    raise ValueError("antecedent supervisor identity")
prior_policy = run_path(POLICY)
need = prior_policy["need"]
MODES = ("COPY", "ALIAS", "WRONG")
WALL, CHILD, MAX_OUT, MAX_READ = 880, 240, 16 << 20, 1 << 30
PASS = "PASS_C291_FIRST_DECODE_ALIAS_AND_MUTANT"
PROTOCOL = "7d89bc4f54e66261484a37733bd5c69a32c4e595385683488344804baacbb529"


def authority(a, prior, svc):
    git = ["/usr/bin/git", "--no-optional-locks", "-C", ROOT]
    need(
        prior.command([*git, "rev-parse", "HEAD"]) == a.commit
        and not prior.command([*git, "status", "--porcelain"]),
        "clean measurement commit",
    )
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C291_CPU0_DECODE_BUILD"
        and build["libs"] == prior.LIBS
        and build["worker_commit"] == "c89c88b342054223e3f27a17fbfd0954803147ac"
        and build["worker_tree"] == "3962daa588dfa89971c60c95ce4c5054bc27fd3f"
        and set(build["executables"]) == {"decode-layer"}
        and build["crypto_sha256"] == prior_policy["CRYPTO"],
        "worker/build identities",
    )
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", build["commit"], a.commit], check=True, timeout=8
    )
    sources = build["source_sha256"]
    need(
        {"build.py", "decode.cpp", "protocol.md"} <= set(sources),
        "native source closure",
    )
    for name, digest in sources.items():
        need(
            Path(name).name == name
            and svc.frozen(ROOT, HERE / name, build["commit"])
            == digest
            == svc.frozen(ROOT, HERE / name, a.commit),
            "changed native source " + name,
        )
    need(sources["protocol.md"] == PROTOCOL, "native protocol")
    exe = a.build_dir / "decode-layer"
    prior.sealed_file(exe, build["executables"]["decode-layer"])
    env = prior.child_env(a, "DENSE")
    listed = prior.command(["/usr/bin/ldd", exe], env)
    need(
        "not found" not in listed and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", listed),
        "CPU-only dependency map",
    )
    actual = {}
    found_crypto = False
    for line in listed.splitlines():
        parts = line.split()
        if parts and (parts[0].startswith("libggml") or parts[0] == "libcrypto.so.3"):
            need(len(parts) >= 3 and parts[1] == "=>", "ELF path")
            p = Path(parts[2]).resolve(strict=True)
            if parts[0].startswith("libggml"):
                need(p.name in prior.LIBS and p.samefile(a.libs / p.name), "GGML source")
                actual[p.name] = prior.sha(p)
            else:
                need(p.samefile("/usr/lib64/libcrypto.so.3"), "unexpected crypto DSO")
                prior.sealed_file(p, prior_policy["CRYPTO"])
                found_crypto = True
    need(
        found_crypto and actual == prior.LIBS and env["CUDA_VISIBLE_DEVICES"] == "",
        "C269 CPU/base DSOs",
    )
    return (
        exe,
        env,
        dict(
            commit=a.commit,
            tree=prior.command([*git, "rev-parse", "HEAD^{tree}"]),
            build_sha256=a.build_sha256,
            binary_sha256=build["executables"]["decode-layer"],
            protocol_sha256=PROTOCOL,
            supervisor_sha256=svc.frozen(ROOT, HERE / "profile.py", a.commit),
            native_sources=sources,
        ),
    )


REF = "8f9b7bb692c9974eac9bca2cb8a4d08436ef83a1e245ba2bbe37442430c6e10f"
PLAN = "1f1caaba34f4581f253691feee436358a8e3bcb2c67b5fd489418f52176510f1"
PRESTATE = "9bc5d91831e50f4f8cacc73f5b34b02542c2c8b5010cb1e620f7ddb7d2101ec6"
PLACED = "adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000"
BEFORE = [[28, 3, 6], [24, -1, 0], [8, 6, 5], [16, 35, 4]]
AFTER = [[28, 3, 6], [24, 14, 6], [8, 6, 5], [16, 35, 4]]


def inputs(a, prior, result):
    r = a.reference_dir
    measured = [
        a.input_dir / "prepare.json",
        r / "receipt.json",
        r / "plan.json",
        a.placement_receipt,
        a.prestate_receipt,
    ]
    prep, ref, plan, placement, state = [
        prior.sealed_json(p, h)
        for p, h in zip(measured, (prior_policy["PREP"], REF, PLAN, PLACED, PRESTATE), strict=True)
    ]
    need(
        ref["status"] == "PASS_REUSED_C127_CPU0_DECODE0_GOLD"
        and ref["plan_sha256"] == state["plan_sha256"] == PLAN
        and ref["placed_pack_receipt_sha256"] == PLACED,
        "capture provenance",
    )
    keys = [k[0] for k in AFTER]
    need(
        plan["position"] == 189
        and plan["layer"] == 0
        and ref["logical_ranks"] == plan["logical_order"] == keys
        and len(state["ranks"]) == 4,
        "captured decode position and routing",
    )
    need(
        [[j["expert"], j["consumer_slot"], j["consumer_generation"]] for j in state["ranks"]]
        == AFTER,
        "captured consumer state",
    )
    need(
        [[j["expert"], j["slot_before"], j["generation_before"]] for j in state["ranks"]] == BEFORE,
        "captured prestate",
    )
    a.pack = Path(placement["destination"])
    st = placement["destination_stat"]
    packstat = dict(
        dev=st["dev"],
        inode=st["ino"],
        size_bytes=st["size"],
        mtime_ns=st["mtime_ns"],
        ctime_ns=st["ctime_ns"],
    )
    need(
        a.pack == a.pack.resolve(strict=True)
        and placement["status"] == "PASS_NVME_C290_FULL_PACK_PLACEMENT"
        and placement["destination_sha256"] == plan["pack_sha256"]
        and placement["destination_device"] == "nvme0n1"
        and placement["destination_transport"] == "nvme"
        and plan["pack_stat"] == packstat
        and prior.token(a.pack) == tuple(packstat.values()),
        "pack placement without rereading file",
    )
    files = ref["row_files_sha256"]
    need(
        len(files) == 7
        and ref["gold_values"] == 2880
        and ref["gold_bytes"] == 11520
        and ref["planned_record_reads_bytes"] == 53035008,
        "captured reference size",
    )
    for tag, h in files.items():
        path = r / (tag + ".bin")
        need(plan["row_file_sha256"][tag] == h, "row hash linkage")
        prior.sealed_file(path, h)
        measured.append(path)
    for name in ("router.weight", "router.bias"):
        path = a.input_dir / name
        need(plan["router_files_sha256"][name] == prep["file_sha256"][name], "router authority")
        prior.sealed_file(path, prep["file_sha256"][name])
        measured.append(path)
    gold = (r / "ffn_moe_out.bin").read_bytes()
    need(
        len(gold) == 11520
        and hashlib.sha256(gold).hexdigest() == files["ffn_moe_out"]
        and all(math.isfinite(x[0]) for x in struct.iter_unpack("<f", gold)),
        "CPU0 independent gold",
    )
    paths = measured + [a.pack]
    original = [prior.token(p) for p in paths]

    def check_files():
        need([prior.token(p) for p in paths] == original, "changed input or NVMe inode")

    result.update(
        reference_sha256=REF,
        plan_sha256=PLAN,
        prestate_sha256=PRESTATE,
        placement_sha256=PLACED,
        input_sha256=prior_policy["PREP"],
        gold_sha256=files["ffn_moe_out"],
        direct_pack_fd_stat=packstat,
    )
    return sum(p.stat().st_size for p in measured) + len(gold), check_files, gold, packstat


def verify(row, mode, folder, gold, packstat, a, prior):
    wrong = mode == "WRONG"
    expect = dict(
        status="PASS_C291_CPU0_DECODE_HANDOFF",
        mode=mode,
        joined_workers=4,
        pack_stat=packstat,
        before=BEFORE,
        after=AFTER,
        setup_reads=3,
        setup_bytes=39776256,
        decode_reads=1,
        decode_bytes=13258752,
        hits=3,
        misses=1,
        copy_bytes=39665664 if mode == "COPY" else 0,
        mismatched_components=[[28, 0], [24, 0]] if wrong else [],
        equal_components=22 if wrong else 24,
        finite=True,
        mmid_nodes=3,
        add_id_nodes=3,
        router_positions=1,
    )
    for k, v in expect.items():
        need(type(row.get(k)) is type(v) and row[k] == v, "native decode witness " + k)
    need(set(row["providers"]) == {"cpu", "base", "crypto"}, "in-process providers")
    for label, soname in prior.LIB_CODES.items():
        path = Path(row["providers"][label])
        need(
            path.is_absolute()
            and path.samefile(a.libs / soname)
            and prior.sha(path) == prior.LIBS[soname],
            "in-process GGML provider",
        )
    cp = Path(row["providers"]["crypto"])
    need(
        cp.is_absolute()
        and cp.samefile("/usr/lib64/libcrypto.so.3")
        and prior.sha(cp) == prior_policy["CRYPTO"],
        "in-process crypto provider",
    )
    path = folder / "decode.f32"
    need(
        list(folder.iterdir()) == [path]
        and not path.is_symlink()
        and path.stat().st_size == len(gold),
        "sole full decode output",
    )
    raw = path.read_bytes()
    need(all(math.isfinite(x[0]) for x in struct.iter_unpack("<f", raw)), "nonfinite decode")
    unequal = sum(
        x != y
        for x, y in zip(struct.iter_unpack("<I", gold), struct.iter_unpack("<I", raw), strict=True)
    )
    need(
        type(row["unequal"]) is int and row["unequal"] == unequal and (unequal > 0) == wrong,
        "independent full decode bits",
    )
    return dict(floats=2880, unequal=unequal, sha256=hashlib.sha256(raw).hexdigest())


def child(a, mode, folder, arm, exe, env, monitor, prior, used):
    native = folder / "native"
    start = time.monotonic()
    p = None
    try:
        monitor.check()
        age = (datetime.now(UTC) - datetime.fromisoformat(arm["c118"]["last_utc"])).total_seconds()
        need(0 <= age <= 3, "expired C118 at launch")
        with (folder / "stdout").open("xb") as out, (folder / "stderr").open("xb") as err:
            p = subprocess.Popen(
                [exe, a.input_dir, a.reference_dir, a.pack, mode, native],
                cwd=ROOT,
                env=env,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            arm.update(pid=p.pid, child_started=True)
            while True:
                monitor.check()
                need(
                    time.monotonic() - start < CHILD
                    and prior.footprint(a.new_output_dir) + 65536 < MAX_OUT,
                    "child wall/output cap",
                )
                # Keep the exited child unreaped until the final Linux I/O census is read.
                finished = os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                io = Path(f"/proc/{p.pid}/io").read_text()
                rchar = int(next(x.split()[1] for x in io.splitlines() if x.startswith("rchar:")))
                need(
                    used + rchar <= MAX_READ, "logical read ceiling including inherited process I/O"
                )
                if finished:
                    arm.update(
                        rc=p.wait(timeout=1),
                        rchar_bytes=rchar,
                        child_wall_s=time.monotonic() - start,
                    )
                    break
                time.sleep(0.08)
        need(arm["rc"] == 0, "nonzero child exit")
        return json.loads((folder / "stdout").read_bytes())
    finally:
        if p is not None:
            monitor.bounded.stop_own_group(p)
            arm["rc"] = p.returncode
        for filename in ("stdout", "stderr"):
            if (folder / filename).is_file():
                arm[filename + "_sha256"] = prior.sha(folder / filename)


def run(a, result):
    prior, svc = prior_policy["shared"]()
    svc.WALL = WALL
    a.checkout = ROOT
    a.input_sha256 = prior_policy["PREP"]
    exe, env, identity = authority(a, prior, svc)
    result.update(identity)
    # Measure cgroup before authenticating any weight material.
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import run_bounded as bounded

    cg = bounded.cgroup_state()
    need(
        cg
        and cg["path"].endswith("/" + a.unit + ".scope")
        and cg["memory_max"] == cg["memory_high"] == svc.CAP
        and cg["swap_max"] == cg["swap_current"] == 0
        and cg["memory_peak"] < svc.STOP,
        "bounded family",
    )
    window = run_path(QUAL / "nvme_admission/window.py")
    gate = prior.sealed_json(a.c55_receipt, a.c55_sha256)
    frozen = prior.sealed_json(
        a.c55_receipt.with_name("resource-policy.json"), gate["canonical_policy_sha256"]
    )
    need(gate["status"] == "PASS_RESOURCE_WINDOW_ONLY" and not gate["reason"], "C55 rejected")
    prior_policy["live_admission"](frozen, window)
    result["monitor_provider"], provider_check = svc.monitor_provider(prior)
    used, check_files, gold, pack_id = inputs(a, prior, result)
    result["supervisor_input_bytes"] = used
    contrasts = []
    for mode in MODES:
        folder = a.new_output_dir / mode
        folder.mkdir()
        (folder / "raw").mkdir()
        arm = dict(mode=mode, status="FAIL_PRESERVED", child_started=False)
        result["arms"].append(arm)
        try:
            prior_policy["live_admission"](frozen, window)
            provider_check()
            check_files()
            guard, policy, bound, cgpath = svc.admit(
                a, prior, QUAL / "packed_real_layer", arm, folder
            )
            monitor = prior_policy["with_live_admission"](svc.Monitor, frozen, window)(
                guard,
                policy,
                bound,
                cgpath,
                folder / "raw/samples.jsonl",
                result["_tic"],
                elapsed_limit=WALL,
            )
            thread = threading.Thread(target=monitor.run, daemon=True)
            thread.start()
            try:
                row = child(a, mode, folder, arm, exe, env, monitor, prior, used)
                arm["gold_comparison"] = verify(
                    row, mode, folder / "native", gold, pack_id, a, prior
                )
                arm["proof"] = row
                used += arm["rchar_bytes"]
                contrasts.append((row["before"], row["after"]))
            finally:
                monitor.end.set()
                thread.join(timeout=6)
                need(not thread.is_alive(), "monitor join")
                monitor.check()
            check_files()
            provider_check()
            need(
                (cgpath / "cgroup.procs").read_text().split() == [str(os.getpid())],
                "unreaped children",
            )
            arm.update(
                status="PASS_DECODE_ARM",
                samples=monitor.count,
                monitor_sha256=prior.sha(folder / "raw/samples.jsonl"),
            )
        finally:
            prior.put(folder / "receipt.json", arm)
    need(
        contrasts[0] == contrasts[1] == contrasts[2]
        and prior.footprint(a.new_output_dir) + 65536 < MAX_OUT,
        "family contrast and output cap",
    )
    result.update(
        status=PASS,
        final_cgroup=bounded.cgroup_state(),
        logical_read_upper_bytes=used,
        c55_sha256=a.c55_sha256,
        full_model_forwards=0,
        gpu_compute=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "build-dir",
        "input-dir",
        "libs",
        "c55-receipt",
        "reference-dir",
        "placement-receipt",
        "prestate-receipt",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=lambda x: Path(x).resolve(), required=True)
    for key in ("unit", "commit", "build-sha256", "c55-sha256"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    r = dict(status="FAIL_PRESERVED", unit=a.unit, arms=[], _tic=time.monotonic())

    def deadline(*_):
        raise TimeoutError("family time limit")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(WALL)
    try:
        run(a, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=repr(exc))
    finally:
        signal.alarm(0)
        r.update(elapsed_s=time.monotonic() - r.pop("_tic"))
        with (a.new_output_dir / "receipt.json").open("x") as f:
            json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
            f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] != PASS)


if __name__ == "__main__":
    raise SystemExit(main())
