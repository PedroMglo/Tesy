"""Build, supervise, or verify the fixed four-worker delivery study on the Tesy laptop."""

import argparse
import gzip
import json
import os
import subprocess
import threading
import time
from itertools import product
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CORE = run_path(HERE.parent / "run.py")
G = run_path(HERE / "grade.py")
C = G["C"]
mm, P, Q, ROOT = (CORE[k] for k in ("mm", "P", "Q", "ROOT"))
read, save, pin, sha, need = (CORE[k] for k in ("read", "save", "pin", "sha", "need"))
SOURCES = ("protocol.md", "cases.py", "grade.py", "service.cpp", "run.py")
CASES = tuple(product(C["JOURNALS"], C["CASES"], G["REGIMES"]))


def authority(a):
    libs, env = CORE["base"](a)
    pin(HERE / "protocol.md", C["METHOD"])
    pin(HERE.parent / "evidence-groups-20261128-r01/decision.json", C["PARENT"])
    return libs, env


def build(a, out, rec):
    libs, env = authority(a)
    group = CORE["L"]["BUILD"]["cgroup"](2 << 30)
    cc = pin(Path("/usr/bin/g++-15"), CORE["CPU_COMPILER"])
    crypto = pin(Path("/usr/lib64/libcrypto.so.3"), P["CRYPTO"])
    header = pin(
        a.backend / "vendor/nlohmann/json.hpp",
        "aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63",
    )
    exe = out / "group-service"
    cmd = list(
        map(
            str,
            [
                cc,
                "-std=c++20",
                "-O2",
                "-g0",
                "-fno-fast-math",
                "-ffp-contract=off",
                "-pthread",
                "-I" + str(a.backend / "ggml/include"),
                "-I" + str(header.parent.parent),
                HERE / "service.cpp",
                *libs.values(),
                crypto,
                "-o",
                exe,
            ],
        )
    )
    rec.update(
        method=C["METHOD"],
        compiler_sha256=sha(cc),
        crypto=sha(crypto),
        command=cmd,
        backend=mm.PIN,
        sources={n: sha(HERE / n) for n in SOURCES},
    )
    save(out / "provenance.json", rec)
    with (out / "compile.log").open("xb") as f:
        subprocess.run(
            cmd, stdout=f, stderr=subprocess.STDOUT, cwd=out, env=env, check=True, timeout=60
        )
    providers = mm.loader(exe, env, libs)
    closure = subprocess.check_output(
        ["/lib64/ld-linux-x86-64.so.2", "--list", exe], env=env, text=True
    )
    need(
        [
            Path(row.split()[2]).resolve()
            for row in closure.splitlines()
            if row.strip().startswith("libcrypto.so.3 =>")
        ]
        == [crypto.resolve()],
        "runtime SHA provider",
    )
    rec.update(
        status="BUILT_GROUP_SERVICE",
        elf=sha(exe),
        providers=providers,
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=int((group / "memory.swap.peak").read_text()),
    )


def prepare(a, out, rec):
    scenarios = C["prepare"](a.archive)
    meta = read(pin(a.manifest / "receipt.json", P["MANIFEST_RECEIPT"]))
    index = read(pin(a.manifest / "integral-index.json", P["INDEX"]))
    pack = Path(meta["pack_path"])
    need(
        P["fd_stat"](pack.stat()) == meta["pack_stat"]
        and meta["pack_sha256"] == P["PACK"]
        and meta["model_sha256"]
        == "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
        and index["stride"] == 13258752
        and index["weight_window"] == G["WINDOW"],
        "target pack or model",
    )
    keys = set()
    expected = 0
    for tag, case, regime in CASES:
        s = scenarios[tag][case]
        jobs = s["jobs"]
        keys.update(k[3] for k in s["demands"])
        keys.update(j["old"] for j in jobs)
        bootstrap = {j["old"] for j in jobs} | {k[3] for k in s["entry"]}
        bootstrap.update(j["expert"] for j in jobs if j["hit"] or regime == "HANDOFF")
        expected += 2 * len(bootstrap)
        if regime == "BANK":
            roles = C["role_names"](case, regime, s)
            miss = sum(not j["hit"] for j in jobs)
            expected += 16 * (len(jobs) + (len(roles) - 1) * miss) + miss
    need(expected * G["WINDOW"] < 40 << 30, "prospective volume")
    records = {}
    for e in sorted(keys):
        row = index["experts"][e]
        parts = row["components"][:3]
        need(
            (row["layer"], row["expert"], row["tier"], row["pack_offset"])
            == (0, e, "CPU", e * index["stride"])
            and all(
                (c["name"], c["type"], c["size_bytes"], c["packed_relative_offset"])
                == ("blk.0.ffn_" + role + "_exps.weight", "mxfp4", 4406400, k * 4406400)
                for k, (role, c) in enumerate(zip(P["ROLES"], parts, strict=True))
            ),
            "target weight matrix",
        )
        records[str(e)] = dict(offset=row["pack_offset"], sha=[c["sha256"] for c in parts])
    plan = out / "plan.json"
    save(
        plan,
        dict(pack=str(pack), pack_stat=meta["pack_stat"], scenarios=scenarios, records=records),
    )
    save(out / "scenarios.json", scenarios)
    rec.update(
        model=meta["model_sha256"],
        pack=P["PACK"],
        pack_stat=meta["pack_stat"],
        index=P["INDEX"],
        plan_sha256=sha(plan),
        scenarios_sha256=sha(out / "scenarios.json"),
        expected_pack_B=expected * G["WINDOW"],
    )
    return plan, scenarios, pack


def physical(a, out, rec, start):
    libs, env = authority(a)
    frozen = read(pin(a.build_dir / "receipt.json", a.build_sha256))
    exe = pin(a.build_dir / "group-service", frozen["elf"])
    need(
        frozen["status"] == "BUILT_GROUP_SERVICE"
        and frozen["commit"] == a.commit
        and frozen["sources"] == {n: sha(HERE / n) for n in SOURCES}
        and mm.loader(exe, env, libs) == frozen["providers"],
        "compiled source and providers",
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
    rec.update(
        c55=a.c55_sha256,
        build=a.build_sha256,
        elf=frozen["elf"],
        backend=mm.PIN,
        providers=frozen["providers"],
        host=os.uname().nodename,
        kernel=os.uname().release,
        cpu=c55["cpu"],
        gpu=c55["gpu_name"],
        gpu_driver=c55["gpu_driver"],
        power=c55["power"],
        disk=c55["model_device"],
        energy_J=None,
        caps=dict(
            wall_s=360,
            memory_B=svc.CAP,
            stop_B=svc.STOP,
            swap_B=0,
            output_B=48 << 20,
            pack_B=40 << 30,
        ),
    )
    plan, scenarios, pack = prepare(a, out, rec)
    (out / "raw").mkdir()
    rec["monitor_provider"], check_provider = svc.monitor_provider(prior)
    check_provider()
    guard, dynamic, bounded, group = svc.admit(a, prior, Q / "packed_real_layer", rec, out)
    mon = P["with_live_admission"](svc.Monitor, policy, window)(
        guard, dynamic, bounded, group, out / "monitor.jsonl", start, elapsed_limit=360
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "memory high")
    save(out / "provenance.json", rec)
    native = {"-".join(c): {} for c in CASES}
    monitor = threading.Thread(target=mon.run, daemon=True)
    monitor.start()
    try:
        for phase in ("exact", "price"):
            for tag, case, regime in CASES:
                key = "-".join((tag, case, regime))
                stage = key + "-" + phase
                rec["stage"] = stage
                CORE["invoke"]([exe, plan, tag, case, regime, phase], stage, out, env, mon)
                data = read(out / (stage + ".json"))
                with (out / "raw" / (stage + ".jsonl")).open() as f:
                    need(
                        [json.loads(line) for line in f] == data["rows"],
                        "incremental trial evidence",
                    )
                G["verify"](data, scenarios[tag][case], tag, case, regime, phase)
                native[key][phase] = data
        decision = G["grade"](scenarios, native)
        need(decision["pack_requested_B"] == rec["expected_pack_B"], "byte conservation")
        save(out / "decision.json", decision)
        with (out / "samples.json.gz").open("xb") as f:
            f.write(
                gzip.compress(
                    json.dumps(native, separators=(",", ":"), sort_keys=True).encode(), mtime=0
                )
            )
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
        P["fd_stat"](pack.stat()) == rec["pack_stat"]
        and not int((group / "memory.swap.peak").read_text())
        and (group / "cgroup.procs").read_text().split() == [str(os.getpid())]
        and prior.footprint(out) < 48 << 20,
        "pack, cgroup or terminal footprint",
    )
    rec.update(
        status="MEASURED_GROUP_SERVICE",
        decision=decision["status"],
        grade_sha256=sha(out / "decision.json"),
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=0,
        HTTP_requests=0,
        full_model_forwards=0,
        gpu_compute=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="mode", required=True)
    modes.add_parser("check").add_argument("evidence", type=Path)
    for name in ("build", "physical"):
        sub = modes.add_parser(name)
        sub.add_argument("--commit", required=True)
        for k in ("backend", "new-output-dir"):
            sub.add_argument("--" + k, type=Path, required=True)
        if name == "physical":
            for k in ("build-dir", "manifest", "archive", "c55-receipt"):
                sub.add_argument("--" + k, type=Path, required=True)
            for k in ("build-sha256", "c55-sha256", "unit"):
                sub.add_argument("--" + k, required=True)
    a = p.parse_args()
    if a.mode == "check":
        native = json.loads(gzip.decompress((a.evidence / "samples.json.gz").read_bytes()))
        res = G["grade"](read(a.evidence / "scenarios.json"), native)
        need(res == read(a.evidence / "decision.json"), "published native decision")
        print(res["status"], res["graded_submissions"], res["pack_requested_B"])
        return
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    rec = dict(
        status="FAIL_PRESERVED", commit=a.commit, tree=mm.git(ROOT, "rev-parse", "HEAD^{tree}")
    )
    try:
        if a.mode == "build":
            build(a, out, rec)
        else:
            physical(a, out, rec, start)
    except Exception as exc:
        rec.update(status="FAIL_PRESERVED", reason=repr(exc))
    rec["elapsed_s"] = time.monotonic() - start
    save(out / ".receipt.tmp", rec)
    (out / ".receipt.tmp").rename(out / "receipt.json")
    print(rec["status"], rec.get("reason", rec.get("decision", "")), flush=True)
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))


if __name__ == "__main__":
    main()
