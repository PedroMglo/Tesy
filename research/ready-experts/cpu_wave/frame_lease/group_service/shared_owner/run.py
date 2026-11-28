"""Build the isolated C291 overlay and grade native cross-layer projections on the laptop."""

import argparse
import os
import subprocess
import threading
import time
from array import array
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(HERE.parent / "run.py")
CORE, mm, P, Q, ROOT, read, save, pin, sha, need = (
    A[k] for k in ("CORE", "mm", "P", "Q", "ROOT", "read", "save", "pin", "sha", "need")
)
W = run_path(Q / "packed_worker/run.py")
METHOD = "8c6a35f763449eccce7eec665d2fb71402f70eac7d8f6cdeb89cf5782e50376a"
FILES = ("protocol.md", "run.py", "fixture.cpp", "runtime.patch")
ROLES = ("STAGED", "SHARED", "WRONG")
SPAN = 2880 * 4


def authority(a):
    pin(HERE / "protocol.md", METHOD)
    return A["authority"](a)


def build(a, out, rec):
    libs, env = authority(a)
    group = CORE["L"]["BUILD"]["cgroup"](2 << 30)
    private = out / "source"
    files = W["extract"](a.backend, private)
    cc = pin(Path("/usr/bin/g++-15"), CORE["CPU_COMPILER"])
    crypto = pin(Path("/usr/lib64/libcrypto.so.3"), P["CRYPTO"])
    patches = (Q / "packed_worker/arena.patch", HERE / "runtime.patch")
    binpath = out / "owner"
    cmd = list(
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
                "-DTESY_C47_CPU_SKIP_PARKED",
                "-pthread",
                "-ffunction-sections",
                "-fdata-sections",
                *["-I" + str(private / p) for p in ("src", "include", "ggml/include")],
                HERE / "fixture.cpp",
                *(private / "src" / s for s in W["BUILD_INPUTS"]),
                "-Wl,--gc-sections",
                "-Wl,--wrap=pread",
                "-Wl,--wrap=ggml_backend_tensor_set",
                *libs.values(),
                crypto,
                "-ldl",
                "-o",
                binpath,
            ],
        )
    )
    rec.update(
        native_commit=W["PIN"],
        native_tree=W["TREE"],
        compiler=sha(cc),
        crypto=sha(crypto),
        original_files=files,
        patches={str(p.relative_to(ROOT)): sha(p) for p in patches},
        sources={p: sha(HERE / p) for p in FILES},
        command=cmd,
    )
    save(out / "provenance.json", rec)
    with (out / "compile.log").open("xb") as log:
        for patch in patches:
            subprocess.run(
                ["patch", "--batch", "--forward", "--fuzz=0", "-d", private, "-p1", "-i", patch],
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=5,
            )
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=100)
    rec.update(
        status="BUILT_SHARED_OWNER",
        elf=sha(binpath),
        providers=mm.loader(binpath, env, libs),
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=int((group / "memory.swap.peak").read_text()),
    )


def plan(a, out):
    meta = read(pin(a.manifest / "receipt.json", P["MANIFEST_RECEIPT"]))
    index = read(pin(a.manifest / "integral-index.json", P["INDEX"]))
    pack = Path(meta["pack_path"])
    need(
        P["fd_stat"](pack.stat()) == meta["pack_stat"]
        and meta["pack_sha256"] == P["PACK"]
        and meta["model_sha256"]
        == "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
        "original pack",
    )
    records = []
    for layer in (0, 24):
        for expert in (47, 82, 75, 52):
            row = index["experts"][layer * 128 + expert]
            need(
                (row["layer"], row["expert"], row["tier"], row["pack_offset"])
                == (layer, expert, "CPU", (layer * 128 + expert) * 13258752),
                "source record",
            )
            matrices = row["components"][:3]
            need(
                all(
                    (m["name"], m["type"], m["size_bytes"], m["packed_relative_offset"])
                    == (f"blk.{layer}.ffn_{role}_exps.weight", "mxfp4", 4406400, k * 4406400)
                    for k, (role, m) in enumerate(zip(P["ROLES"], matrices, strict=True))
                ),
                "three original matrices",
            )
            records.append(
                dict(
                    layer=layer,
                    expert=expert,
                    offset=row["pack_offset"],
                    sha=[m["sha256"] for m in matrices],
                )
            )
    data = dict(pack=str(pack), pack_stat=meta["pack_stat"], records=records)
    save(out / "plan.json", data)
    return data


def grade(rows, differences):
    need(set(rows) == set(ROLES) and set(differences) == set(ROLES[1:]), "all three arms")
    for role, r in rows.items():
        shared = role != "STAGED"
        addresses = [list(range(1248, 1252)) if shared else list(range(4)), list(range(4))]
        need(
            r["role"] == role
            and r["owners"] == r["data_buffers"] == (1 if shared else 25)
            and r["views"] == 75
            and r["addressed_records"] == (1252 if shared else 1000)
            and r["requested_pack_B"] == 8 * 13221888
            and r["sets"] == 24
            and r["reads"] == 8
            and r["workers"] == 4
            and 0 < r["reading_workers"] <= 4,
            "storage and actual service",
        )
        for i, (visit, expected) in enumerate(zip(r["visits"], (0, 1, 0), strict=True)):
            p = visit["projections"]
            need(
                visit["frames"] == addresses[expected]
                and visit["layer"] == 24 * expected
                and visit["computed"] == addresses[1 if i == 2 and role == "WRONG" else expected]
                and visit["reads_after"] == (4 if i == 0 else 8)
                and len(p["sha256"]) == 3
                and p["splits"] == 1,
                "CPU rank view, scheduler or unexpected load",
            )
            for k, h in enumerate(p["sha256"]):
                match = h == rows["STAGED"]["visits"][i]["projections"]["sha256"][k]
                if role != "STAGED":
                    count = differences[role][3 * i + k]
                    need(0 <= count <= SPAN and (count == 0) == match, "raw equality vs digest")
                need(
                    match == (role != "WRONG" or i != 2),
                    "changed correct or unchanged wrong projection",
                )
    return dict(
        status="GO_NATIVE_SHARED_CPU_OWNER",
        evidence="MEASURED_C291_LOADER_WORKERS_CPU_SCHEDULER",
        roles=rows,
        differing_F32_per_projection=differences,
        F32_per_role=9 * SPAN,
        packed_reads_B=3 * 8 * 13221888,
        model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
        M3="PARTIAL",
        M4="NOT_MET",
    )


def physical(a, out, rec, start):
    libs, env = authority(a)
    build = read(pin(a.build_dir / "receipt.json", a.build_sha256))
    exe = pin(a.build_dir / "owner", build["elf"])
    need(
        build["status"] == "BUILT_SHARED_OWNER"
        and build["commit"] == a.commit
        and build["sources"] == {p: sha(HERE / p) for p in FILES}
        and mm.loader(exe, env, libs) == build["providers"],
        "frozen build",
    )
    prior, svc = P["shared"]()
    svc.WALL = 240
    a.checkout = ROOT
    c55 = read(pin(a.c55_receipt, a.c55_sha256))
    policy = read(
        pin(a.c55_receipt.parent / "resource-policy.json", c55["canonical_policy_sha256"])
    )
    window = run_path(Q / "nvme_admission/window.py")
    P["live_admission"](policy, window)
    data = plan(a, out)
    rec.update(
        c55=a.c55_sha256,
        build=a.build_sha256,
        elf=build["elf"],
        providers=build["providers"],
        host=os.uname().nodename,
        kernel=os.uname().release,
        cpu=c55["cpu"],
        gpu=c55["gpu_name"],
        gpu_driver=c55["gpu_driver"],
        power=c55["power"],
        disk=c55["model_device"],
        model_sha256="582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
        pack=P["PACK"],
        index=P["INDEX"],
        plan_sha256=sha(out / "plan.json"),
        energy_J=None,
        caps=dict(
            wall_s=240,
            memory_B=svc.CAP,
            stop_B=svc.STOP,
            swap_B=0,
            output_B=64 << 20,
            pack_B=1 << 30,
        ),
    )
    rec["monitor_provider"], check_provider = svc.monitor_provider(prior)
    check_provider()
    (out / "raw").mkdir()
    guard, dynamic, bounded, group = svc.admit(a, prior, Q / "packed_real_layer", rec, out)
    mon = P["with_live_admission"](svc.Monitor, policy, window)(
        guard, dynamic, bounded, group, out / "monitor.jsonl", start, elapsed_limit=240
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "scope high")
    save(out / "provenance.json", rec)
    monitor = threading.Thread(target=mon.run, daemon=True)
    monitor.start()
    try:
        rows = {}
        values = {}
        for role in ROLES:
            rec["stage"] = role
            target = out / (role + ".f32")
            CORE["invoke"]([exe, out / "plan.json", role, target], role, out, env, mon)
            rows[role] = read(out / (role + ".json"))
            values[role] = array("I")
            values[role].frombytes(target.read_bytes())
            need(values[role].itemsize == 4 and len(values[role]) == 9 * SPAN, "all raw F32 bits")
        differences = {}
        for role in ROLES[1:]:
            differences[role] = [
                sum(
                    x != y
                    for x, y in zip(
                        values["STAGED"][k * SPAN : (k + 1) * SPAN],
                        values[role][k * SPAN : (k + 1) * SPAN],
                        strict=True,
                    )
                )
                for k in range(9)
            ]
        result = grade(rows, differences)
        save(out / "decision.json", result)
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
        "final resources",
    )
    rec.update(
        status="MEASURED_SHARED_OWNER",
        decision=result["status"],
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=0,
        model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="mode", required=True)
    commands.add_parser("check").add_argument("receipt", type=Path)
    for mode in ("build", "physical"):
        sub = commands.add_parser(mode)
        sub.add_argument("--commit", required=True)
        for k in ("backend", "new-output-dir"):
            sub.add_argument("--" + k, type=Path, required=True)
        if mode == "physical":
            for k in ("build-dir", "c55-receipt", "manifest"):
                sub.add_argument("--" + k, type=Path, required=True)
            for k in ("build-sha256", "c55-sha256", "unit"):
                sub.add_argument("--" + k, required=True)
    a = p.parse_args()
    if a.mode == "check":
        d = read(a.receipt)
        need(d == grade(d["roles"], d["differing_F32_per_projection"]), "compact publication")
        print(d["status"])
        return
    os.umask(0o077)
    start = time.monotonic()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
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
