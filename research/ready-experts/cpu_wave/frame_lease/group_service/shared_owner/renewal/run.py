"""Compile, run and verify the native renewal family in a bounded scope."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import threading
import time
from array import array
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
N = run_path(HERE.parent / "run.py")
A, CORE, mm, P, Q, ROOT, W, read, save, pin, sha, need = (
    N[k] for k in ("A", "CORE", "mm", "P", "Q", "ROOT", "W", "read", "save", "pin", "sha", "need")
)
G = run_path(HERE / "grade.py")
METHOD = "2984b194212a95d696689fe5e433eebc93ea35363a071abcdd89b61e1b4bdaf3"
BASE = "e76fa7596c7354db03d9715e4544304e34d3c0c1f35c573cba182d1139b45031"
SCENARIOS = "ab8cc2eaed4deeedd5c8956d8cb2db428193b072ee1bc9dfd7357e47e1bb9334"
FILES = (
    "protocol.md",
    "fixture.cpp",
    "cpu-weight-bank.h",
    "runtime.patch",
    "grade.py",
    "run.py",
    "check_bank.cpp",
)


def authority(a):
    pin(HERE / "protocol.md", METHOD)
    baseline = read(pin(HERE.parent / "evidence-20261128-r01/decision.json", BASE))
    need(baseline["status"] == "GO_NATIVE_SHARED_CPU_OWNER", "integrated owner gate")
    return N["authority"](a)


def build(a, out, rec):
    libs, env = authority(a)
    group = CORE["L"]["BUILD"]["cgroup"](2 << 30)
    source = out / "source"
    files = W["extract"](a.backend, source)
    patches = (
        Q / "packed_worker/arena.patch",
        HERE.parent / "runtime.patch",
        HERE / "runtime.patch",
    )
    cc = pin(Path("/usr/bin/g++-15"), CORE["CPU_COMPILER"])
    crypto = pin(Path("/usr/lib64/libcrypto.so.3"), P["CRYPTO"])
    saved = read(HERE.parent / "evidence-20261128-r01/build.json")
    need(
        sha(cc) == saved["compiler"]
        and sha(HERE.parent / "fixture.cpp") == saved["sources"]["fixture.cpp"],
        "fixed control helpers",
    )
    exe = out / "renewal"
    cc_args = list(
        map(
            str,
            [
                cc,
                "-std=c++20",
                "-O1",
                "-g0",
                "-fno-fast-math",
                "-ffp-contract=off",
                "-DTESY_STORE_TESTING",
                "-DTESY_CPU_RENEWAL_TEST",
                "-DTESY_C47_CPU_SKIP_PARKED",
                "-pthread",
                "-ffunction-sections",
                "-fdata-sections",
                *["-I" + str(source / p) for p in ("src", "include", "ggml/include")],
                HERE / "fixture.cpp",
                *(source / "src" / p for p in W["BUILD_INPUTS"]),
                "-Wl,--gc-sections",
                "-Wl,--wrap=pread",
                "-Wl,--wrap=ggml_backend_tensor_set",
                *libs.values(),
                crypto,
                "-ldl",
                "-o",
                exe,
            ],
        )
    )
    proof = out / "check-bank"
    proof_cmd = list(map(str, [cc, "-std=c++20", "-O2", HERE / "check_bank.cpp", "-o", proof]))
    rec.update(
        native_commit=W["PIN"],
        native_tree=W["TREE"],
        sources={n: sha(HERE / n) for n in FILES},
        compiler=sha(cc),
        crypto=sha(crypto),
        patches={str(p.relative_to(ROOT)): sha(p) for p in patches},
        original_files=files,
        command=cc_args,
        controller_command=proof_cmd,
        protocol=METHOD,
    )
    save(out / "provenance.json", rec)
    shutil.copyfile(HERE / "cpu-weight-bank.h", source / "src/cpu-weight-bank.h")
    with (out / "compile.log").open("xb") as log:

        def run(cmd, limit):
            subprocess.run(
                cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=limit
            )

        for p in patches:
            run(["patch", "--batch", "--forward", "--fuzz=0", "-d", source, "-p1", "-i", p], 5)
        run(proof_cmd, 15)
        run([proof], 5)
        run(cc_args, 85)
    rec.update(
        status="BUILT_NATIVE_RENEWAL",
        elf=sha(exe),
        controller_elf=sha(proof),
        providers=mm.loader(exe, env, libs),
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=int((group / "memory.swap.peak").read_text()),
    )


def prepare(a, out):
    m = read(pin(a.manifest / "receipt.json", P["MANIFEST_RECEIPT"]))
    index = read(pin(a.manifest / "integral-index.json", P["INDEX"]))
    need(
        P["fd_stat"](Path(m["pack_path"]).stat()) == m["pack_stat"]
        and m["pack_sha256"] == P["PACK"]
        and m["model_sha256"] == "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
        "target pack",
    )
    scenarios = read(pin(HERE.parents[1] / "evidence-20261128-r01/scenarios.json", SCENARIOS))
    keys, slots = {}, {}
    for tag, v in scenarios.items():
        jobs = v["decode4"]["jobs"]
        keys[tag] = [[j[k] for j in jobs] for k in ("expert", "old")]
        slots[tag] = [j["slot"] for j in jobs]
    need(
        keys["P106"] == keys["P97"]
        and slots["P106"] == slots["P97"]
        and len(set(keys["P97"][0] + keys["P97"][1])) == 8,
        "two observed groups",
    )
    records = []
    for expert in keys["P97"][0] + keys["P97"][1]:
        row = index["experts"][expert]
        parts = row["components"][:3]
        need(
            (row["layer"], row["expert"], row["tier"], row["pack_offset"])
            == (0, expert, "CPU", expert * 13258752)
            and all(
                (p["name"], p["type"], p["size_bytes"], p["packed_relative_offset"])
                == (f"blk.0.ffn_{role}_exps.weight", "mxfp4", 4406400, k * 4406400)
                for k, (p, role) in enumerate(zip(parts, P["ROLES"], strict=True))
            ),
            "target matrix mapping",
        )
        records.append(
            dict(expert=expert, offset=row["pack_offset"], sha=[p["sha256"] for p in parts])
        )
    data = dict(
        pack=m["pack_path"],
        pack_stat=m["pack_stat"],
        slots=slots["P97"],
        A=keys["P97"][0],
        B=keys["P97"][1],
        records=records,
    )
    save(out / "plan.json", data)
    return data


def family(exe, out, env, mon, rec):
    base = read(pin(HERE.parent / "evidence-20261128-r01/decision.json", BASE))
    native = dict(
        exact={},
        differences={},
        price=[],
        independent_A=base["roles"]["STAGED"]["visits"][0]["projections"]["sha256"],
    )
    values = {}
    roles = G["ROLES"]
    for role in (*roles, "WRONG", "EIO"):
        stage = "exact-" + role
        raw = out / "raw" / (stage + ".f32")
        rec["stage"] = stage
        CORE["invoke"]([exe, out / "plan.json", role, "exact", raw], stage, out, env, mon)
        d = read(out / (stage + ".json"))
        G["verify"](d, role, True)
        native["exact"][role] = d
        values[role] = array("I")
        values[role].frombytes(raw.read_bytes())
        need(
            values[role].itemsize == 4
            and len(values[role]) == (3 if role == "EIO" else 12) * G["SPAN"],
            "all float bits",
        )
        if role not in ("DISK", "EIO"):
            n = G["SPAN"]
            native["differences"][role] = [
                sum(
                    x != y
                    for x, y in zip(
                        values[role][k * n : (k + 1) * n],
                        values["DISK"][k * n : (k + 1) * n],
                        strict=True,
                    )
                )
                for k in range(12)
            ]
    G["verify_exact"](native["exact"], native["differences"], native["independent_A"])
    for block, direction, role in G["order"]():
        stage = f"price-{block}-{direction}-{role}"
        rec["stage"] = stage
        CORE["invoke"]([exe, out / "plan.json", role, "price", "unused"], stage, out, env, mon)
        d = read(out / (stage + ".json"))
        G["verify"](d, role, False)
        native["price"].append(dict(d, block=block, direction=direction))
    result = G["grade"](native)
    expected_reads = 16 + 8 + 8 + 8 + 8 + 16 * (16 + 8 + 8)
    need(
        result["pack_requested_B"] == expected_reads * G["WINDOW"] <= 16 << 30, "billed pack window"
    )
    packed = gzip.compress(
        json.dumps(native, separators=(",", ":"), sort_keys=True).encode(), mtime=0
    )
    with (out / "samples.json.gz").open("xb") as f:
        f.write(packed)
    save(out / "decision.json", result)
    return result


def physical(a, out, rec, start):
    libs, env = authority(a)
    build = read(pin(a.build_dir / "receipt.json", a.build_sha256))
    exe = pin(a.build_dir / "renewal", build["elf"])
    need(
        build["status"] == "BUILT_NATIVE_RENEWAL"
        and build["commit"] == a.commit
        and build["sources"] == {n: sha(HERE / n) for n in FILES}
        and mm.loader(exe, env, libs) == build["providers"],
        "native build",
    )
    prior, svc = P["shared"]()
    svc.WALL = 360
    a.checkout = ROOT
    c55 = read(pin(a.c55_receipt, a.c55_sha256))
    policy = read(
        pin(a.c55_receipt.parent / "resource-policy.json", c55["canonical_policy_sha256"])
    )
    window = run_path(Q / "nvme_admission/window.py")
    P["live_admission"](policy, window)
    data = prepare(a, out)
    rec.update(
        c55=a.c55_sha256,
        build=a.build_sha256,
        elf=build["elf"],
        providers=build["providers"],
        host=os.uname().nodename,
        kernel=os.uname().release,
        cpu=c55["cpu"],
        gpu=c55["gpu_name"],
        driver=c55["gpu_driver"],
        power=c55["power"],
        disk=c55["model_device"],
        energy_J=None,
        model_sha256="582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
        pack=P["PACK"],
        index=P["INDEX"],
        plan_sha256=sha(out / "plan.json"),
        caps=dict(
            wall_s=360,
            memory_B=svc.CAP,
            stop_B=svc.STOP,
            swap_B=0,
            output_B=64 << 20,
            pack_B=16 << 30,
        ),
    )
    rec["monitor_provider"], check_provider = svc.monitor_provider(prior)
    check_provider()
    (out / "raw").mkdir()
    guard, dynamic, bounded, group = svc.admit(a, prior, Q / "packed_real_layer", rec, out)
    mon = P["with_live_admission"](svc.Monitor, policy, window)(
        guard, dynamic, bounded, group, out / "monitor.jsonl", start, elapsed_limit=360
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "scope high")
    save(out / "provenance.json", rec)
    monitor = threading.Thread(target=mon.run, daemon=True)
    monitor.start()
    try:
        result = family(exe, out, env, mon, rec)
    finally:
        mon.end.set()
        monitor.join(6)
        need(not monitor.is_alive(), "monitor drain")
        mon.check()
        rec.update(
            monitor_samples=mon.count,
            monitor_sha256=sha(out / "monitor.jsonl"),
            cgroup_final=bounded.cgroup_state(),
        )
    check_provider()
    need(
        P["fd_stat"](Path(data["pack"]).stat()) == data["pack_stat"]
        and int((group / "memory.swap.peak").read_text()) == 0
        and (group / "cgroup.procs").read_text().split() == [str(os.getpid())]
        and prior.footprint(out) < 64 << 20,
        "terminal scope",
    )
    rec.update(
        status="MEASURED_NATIVE_RENEWAL",
        decision=result["status"],
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=0,
        model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="mode", required=True)
    modes.add_parser("check").add_argument("evidence", type=Path)
    for mode in ("build", "physical"):
        sub = modes.add_parser(mode)
        sub.add_argument("--commit", required=True)
        for k in ("backend", "new-output-dir"):
            sub.add_argument("--" + k, type=Path, required=True)
        if mode == "physical":
            for k in ("build-dir", "manifest", "c55-receipt"):
                sub.add_argument("--" + k, type=Path, required=True)
            for k in ("build-sha256", "c55-sha256", "unit"):
                sub.add_argument("--" + k, required=True)
    a = p.parse_args()
    if a.mode == "check":
        res = G["grade"](json.loads(gzip.decompress((a.evidence / "samples.json.gz").read_bytes())))
        need(res == read(a.evidence / "decision.json"), "published native evaluation")
        print(res["correctness"], res["status"], res["pack_requested_B"])
        return
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    start = time.monotonic()
    rec = dict(
        status="FAIL_PRESERVED", commit=a.commit, tree=mm.git(ROOT, "rev-parse", "HEAD^{tree}")
    )
    try:
        if a.mode == "build":
            build(a, out, rec)
        else:
            physical(a, out, rec, start)
    except Exception as e:
        rec.update(status="FAIL_PRESERVED", reason=repr(e), detail=str(e))
    rec["elapsed_s"] = time.monotonic() - start
    save(out / ".receipt.tmp", rec)
    (out / ".receipt.tmp").rename(out / "receipt.json")
    print(rec["status"], rec.get("reason", rec.get("decision", "")))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))


if __name__ == "__main__":
    main()
