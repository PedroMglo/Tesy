"""Bounded supervisor for the real CPU0 COPY, ALIAS and incorrect-restoration tiles."""

import argparse
import hashlib
import json
import os
import re
import signal
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
GOLDS = (32, 64, 96)
MODES = ("COPY", "ALIAS", "WRONG")
WALL, CHILD, MAX_OUT, MAX_READ = 880, 240, 16 << 20, 1 << 30
TILE = 32 * 2880 * 4
PASS = "PASS_C291_ALIAS_REAL_CPU0_TILES_AND_MUTANT"
PROTOCOL = "8cb3c290646ab1c67376f6659f51d96caddcf1e71cb5762f60140164008b3799"


def authority(a, prior, svc):
    git = ["/usr/bin/git", "--no-optional-locks", "-C", ROOT]
    need(
        prior.command([*git, "rev-parse", "HEAD"]) == a.commit
        and not prior.command([*git, "status", "--porcelain"]),
        "clean measurement commit",
    )
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C291_ALIAS_REAL_LAYER_BUILD"
        and build["libs"] == prior.LIBS
        and build["worker_commit"] == "c89c88b342054223e3f27a17fbfd0954803147ac"
        and build["worker_tree"] == "3962daa588dfa89971c60c95ce4c5054bc27fd3f"
        and set(build["executables"]) == {"alias-layer"},
        "worker/build identities",
    )
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", build["commit"], a.commit], check=True, timeout=8
    )
    sources = build["source_sha256"]
    need(
        {"build.py", "source.py", "real.h", "layer.inc", "protocol.md"} <= set(sources),
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
    exe = a.build_dir / "alias-layer"
    prior.sealed_file(exe, build["executables"]["alias-layer"])
    env = prior.child_env(a, "DENSE")
    listed = prior.command(["/usr/bin/ldd", exe], env)
    need(
        "not found" not in listed and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", listed),
        "CPU-only dependency map",
    )
    actual = {}
    for line in listed.splitlines():
        parts = line.split()
        if parts and (parts[0].startswith("libggml") or parts[0] == "libcrypto.so.3"):
            need(len(parts) >= 3 and parts[1] == "=>", "ELF path")
            p = Path(parts[2]).resolve(strict=True)
            if parts[0].startswith("libggml"):
                need(p.name in prior.LIBS and p.samefile(a.libs / p.name), "GGML source")
                actual[p.name] = prior.sha(p)
            else:
                prior.sealed_file(p, prior_policy["CRYPTO"])
    need(actual == prior.LIBS and env["CUDA_VISIBLE_DEVICES"] == "", "C269 CPU/base DSOs")
    return (
        exe,
        env,
        dict(
            commit=a.commit,
            tree=prior.command([*git, "rev-parse", "HEAD^{tree}"]),
            build_sha256=a.build_sha256,
            binary_sha256=build["executables"]["alias-layer"],
            protocol_sha256=PROTOCOL,
            supervisor_sha256=svc.frozen(ROOT, HERE / "profile.py", a.commit),
            native_sources=sources,
        ),
    )


def rotated(tiles):
    first, second, last = [r["bindings"] for r in tiles]
    for rows in (first, second, last):
        need(
            len(rows) == 5
            and all(len(x) == 3 and all(type(i) is int for i in x) for x in rows)
            and tuple(x[0] for x in rows) == prior_policy["ACTUAL"]
            and len({r[1] for r in rows}) == 5
            and all(0 <= s < 40 and g > 0 for _, s, g in rows),
            "five active bindings",
        )
    need(first[4] == second[4] == last[4], "identity of 98")
    for i in range(4):
        target = first[(i + 1) % 4]
        need(
            second[i][1:] == [target[1], target[2] + 1]
            and last[i][1:] == [first[i][1], first[i][2] + 2],
            "wrong cyclic destination or generation",
        )


def verify(row, mode, native, gold, pack_id, a, prior):
    expected = dict(
        status="PASS_C291_CPU0_ALIAS_TILES",
        mode=mode,
        joined_workers=4,
        source_reads=5,
        source_bytes=66109440,
        copy_bytes=211550208 if mode == "COPY" else 0,
        pack_stat=pack_id,
        router_positions=153,
    )
    for name, v in expected.items():
        need(type(row.get(name)) is type(v) and row[name] == v, "native proof " + name)
    need(set(row["providers"]) == {"cpu", "base"}, "runtime GGML providers")
    for kind, soname in prior.LIB_CODES.items():
        path = Path(row["providers"][kind])
        need(
            path.is_absolute()
            and path.samefile(a.libs / soname)
            and prior.sha(path) == prior.LIBS[soname],
            "in-process provider " + kind,
        )
    need(
        len(row["transitions"]) == 2
        and all(
            t["workers"] == 4 and t["reservations"] == 4 and t["last_reader"] is True
            for t in row["transitions"]
        ),
        "leases/claims on both transitions",
    )
    need(
        set(x.name for x in native.iterdir()) == {f"tile{i}.f32" for i in GOLDS},
        "native output set",
    )
    tiles = row["tiles"]
    need([item["first"] for item in tiles] == list(GOLDS), "ordered three tiles")
    rotated(tiles)
    measured = []
    for item, n in zip(tiles, GOLDS, strict=True):
        tile = prior_policy["measured_tile"](native / f"tile{n}.f32", gold[n])
        diff = tile["changed_f32_bit_patterns"]
        need(
            tile["finite"]
            and item["finite"] is True
            and item["mmid_nodes"] == 24
            and diff == item["unequal"]
            and (diff > 0) == (mode == "WRONG" and n == 96),
            "independent numerical tile",
        )
        measured.append(tile)
    return measured


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
                [exe, a.input_dir, mode, native],
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
    base_stat = {p.name: prior.token(p) for p in a.input_dir.iterdir()}
    prep, input_state = svc.inputs(a, prior, result)
    need(input_state == base_stat, "prepared material changed during authentication")
    pack_id = prep["pack_identity"]
    raw = (a.input_dir / "ffn_moe_out-0.bin").read_bytes()
    need(hashlib.sha256(raw).hexdigest() == prior.GOLD, "153-position independent gold")
    gold = {n: raw[n * 2880 * 4 : n * 2880 * 4 + TILE] for n in GOLDS}
    # prepare_gate reads prepare.json, all declared inputs, and once more the 32:64 slice.
    used = (
        (a.input_dir / "prepare.json").stat().st_size
        + prep["prepared_files_bytes"]
        + TILE
        + len(raw)
    )
    result.update(supervisor_input_bytes=used, gold_sha256=prior.GOLD)
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
            need(
                base_stat == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
                "changed prepared inputs",
            )
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
                contrasts.append([t["bindings"] for t in row["tiles"]])
            finally:
                monitor.end.set()
                thread.join(timeout=6)
                need(not thread.is_alive(), "monitor join")
                monitor.check()
            need(
                base_stat == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
                "final input identity",
            )
            provider_check()
            need(
                (cgpath / "cgroup.procs").read_text().split() == [str(os.getpid())],
                "unreaped children",
            )
            arm.update(
                status="PASS_REAL_LAYER_ARM",
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
    for key in ("build-dir", "input-dir", "libs", "c55-receipt", "new-output-dir"):
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
