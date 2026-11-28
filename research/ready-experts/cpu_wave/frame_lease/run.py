"""Build and measure the CPU0 last-reader experiment, or reproduce its published arithmetic."""

import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE.parent / "layer.py")
ROOT, mm, P, Q = (L[k] for k in ("ROOT", "mm", "P", "Q"))
GR = run_path(HERE / "grade.py")
need, sha = mm.need, mm.sha
METHOD = "043dd558795c3c883115758e511543dbffb18e27a63adfe0497a87e37d1197c1"
CASES = GR["CASES"]
INPUT = L["INPUT"]
PLACES = {
    "five": "5a484bb41b97dce8645b9e0c046e04fc17f18aeb35c9ce7e20346e4f465256c5",
    "many": "99b7fddcc5bd3ff27d0364b8c5adb8a0cf4f91dea5afa8002fefe2e7eede4098",
}
CPU_COMPILER = "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a"
OPERATOR = (
    Q.parent
    / "ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling"
)
FILES = ("protocol.md", "lease.h", "client.cpp", "grade.py", "run.py")


def read(p):
    return json.loads(p.read_bytes())


def save(p, data):
    with p.open("x") as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def pin(p, h):
    need(sha(p) == h, "identity of " + str(p))
    return p


def base(a):
    need(
        mm.git(ROOT, "rev-parse", "HEAD") == a.commit and not mm.git(ROOT, "status", "--porcelain"),
        "clean Tesy source",
    )
    need(
        mm.git(a.backend, "rev-parse", "HEAD") == mm.PIN
        and not mm.git(a.backend, "status", "--porcelain"),
        "pinned native backend",
    )
    pin(HERE / "protocol.md", METHOD)
    native = pin(
        OPERATOR / "evidence-operator-20261128-r01/operator.json",
        "d0854d6a970c41296cccd602ebe20d00817403a3b65fba9a16f579fc9d6e36e9",
    )
    need(read(native)["status"] == "GO_NATIVE_CPU_FRAME_PROMOTION", "operator admission")
    libs = a.backend / "build-c269-cuda/bin"
    providers = {
        "libggml-cpu.so.0": pin(libs / mm.CPU, mm.CPU_SHA),
        "libggml-base.so.0": pin(libs / mm.BASE, mm.BASE_SHA),
    }
    env = mm.ENV | dict(
        LD_LIBRARY_PATH=str(libs),
        LC_ALL="C",
        OMP_NUM_THREADS="8",
        OMP_DYNAMIC="FALSE",
        TESY_CPU_WAVE_SKIP_PARKED="1",
        TMPDIR=str(a.new_output_dir),
    )
    return providers, env


def build(a, out, rec):
    libs, env = base(a)
    group = L["BUILD"]["cgroup"](2 << 30)
    original = pin(
        Q / "packed_real_layer/layer.cpp",
        "e1240b2981b49163efa9156ac9bc15f7865770f7c1016e26a8ea61ad9d97c14a",
    )
    arith = pin(
        ROOT / "tools/block_expert_reuse_operator.cpp",
        "4ceb573da1196b7612af8c1aa4ab65a4e14f9bfe966d77303e3b6f71de32ad3e",
    )
    text = original.read_text()
    (out / "helpers.inc").write_text(
        text[
            text.index("template<class T> static std::vector<T> read(") : text.index(
                "// Exact two functions"
            )
        ]
    )
    text = arith.read_text()
    (out / "arithmetic.inc").write_text(
        text[text.index("ggml_tensor * pairs(") : text.index("void build(graph_plan")]
    )
    cc = pin(Path("/usr/bin/g++-15"), CPU_COMPILER)
    crypto = pin(Path("/usr/lib64/libcrypto.so.3"), P["CRYPTO"])
    header = pin(
        a.backend / "vendor/nlohmann/json.hpp",
        "aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63",
    )
    exe = out / "frame-layer"
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
                "-I" + str(out),
                "-I" + str(a.backend / "ggml/include"),
                "-I" + str(header.parent.parent),
                HERE / "client.cpp",
                *libs.values(),
                crypto,
                "-o",
                exe,
            ],
        )
    )
    rec.update(
        compiler_sha256=sha(cc),
        crypto=sha(crypto),
        command=cmd,
        method=METHOD,
        original_helpers_sha256=sha(original),
        original_pairs_sha256=sha(arith),
        backend=mm.PIN,
        source_sha256={k: sha(HERE / k) for k in FILES},
        generated={k: sha(out / k) for k in ("helpers.inc", "arithmetic.inc")},
    )
    save(out / "provenance.json", rec)
    with (out / "compile.log").open("xb") as f:
        subprocess.run(
            cmd, stdout=f, stderr=subprocess.STDOUT, cwd=out, env=env, check=True, timeout=60
        )
    rec["providers"] = mm.loader(exe, env, libs)
    closure = subprocess.check_output(
        ["/lib64/ld-linux-x86-64.so.2", "--list", exe], env=env, text=True
    )
    actual_crypto = [
        Path(x.split()[2]).resolve()
        for x in closure.splitlines()
        if x.strip().startswith("libcrypto.so.3 =>")
    ]
    need(actual_crypto == [crypto.resolve()], "actual linked SHA provider")
    rec.update(
        status="BUILT_REAL_LAYER",
        elf=sha(exe),
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=int((group / "memory.swap.peak").read_text()),
    )


def prepare(a, out, receipt):
    inputs, gold, exe, genuine = L["witnesses"](a, out)
    metadata = read(pin(a.manifest / "receipt.json", P["MANIFEST_RECEIPT"]))
    index = read(pin(a.manifest / "integral-index.json", P["INDEX"]))
    pack = Path(gold["pack_path"])
    need(
        metadata["pack_sha256"] == gold["pack_sha256"] == P["PACK"]
        and gold["pack_stat"] == P["fd_stat"](pack.stat()) == metadata["pack_stat"]
        and gold["index_sha256"] == P["INDEX"]
        and index["stride"] == 13258752
        and index["weight_window"] == 13221888,
        "model pack and geometry",
    )
    records = {}
    for i, row in enumerate(index["experts"][:128]):
        need(
            (row["layer"], row["expert"], row["pack_offset"], row["tier"])
            == (0, i, 13258752 * i, "CPU"),
            "layer zero inventory",
        )
        components = row["components"][:3]
        need(
            all(
                c["type"] == "mxfp4"
                and c["size_bytes"] == 4406400
                and c["packed_relative_offset"] == k * 4406400
                and c["name"] == "blk.0.ffn_" + role + "_exps.weight"
                for k, (role, c) in enumerate(zip(P["ROLES"], components, strict=True))
            ),
            "MXFP4 layout",
        )
        records[str(i)] = dict(offset=row["pack_offset"], sha=[c["sha256"] for c in components])
    monodir = a.archive_part / "tesy-c269-dispatch-exact-20261126-r02/1-MONO"
    places = {}
    for case, saved in zip(CASES, ("low-0-five", "high-0-many"), strict=True):
        key = monodir / saved / "physical"
        pin(key, PLACES[case])
        places[case] = str(key)
    plan = out / "plan.json"
    save(
        plan,
        dict(
            inputs=str(inputs),
            pack=str(pack),
            pack_stat=gold["pack_stat"],
            places=places,
            records=records,
        ),
    )
    receipt.update(
        method=METHOD,
        prepare=INPUT,
        archive_part=L["SOURCE"],
        plan=sha(plan),
        pack=metadata["pack_sha256"],
        model=metadata["model_sha256"],
        pack_index=P["INDEX"],
        pack_stat=gold["pack_stat"],
        physical_ids=PLACES,
        target_hashes={n: h for n, h in gold["input_sha256"].items() if n.split("/")[0] in CASES},
    )
    return plan, inputs, exe, gold, genuine


def invoke(cmd, name, out, env, mon):
    with (
        (out / (name + ".json")).open("xb") as stdout,
        (out / (name + ".log")).open("xb") as stderr,
    ):
        with subprocess.Popen(
            cmd, cwd=out, env=env, stdout=stdout, stderr=stderr, start_new_session=True
        ) as child:
            try:
                while child.poll() is None:
                    mon.check()
                    try:
                        child.wait(0.15)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                mon.bounded.stop_own_group(child)
            need(child.returncode == 0, "native " + name)


def physical(a, out, rec, start):
    libs, env = base(a)
    frozen = read(pin(a.build_dir / "receipt.json", a.build_sha256))
    binary = pin(a.build_dir / "frame-layer", frozen["elf"])
    need(
        frozen["status"] == "BUILT_REAL_LAYER"
        and frozen["commit"] == a.commit
        and frozen["source_sha256"] == {n: sha(HERE / n) for n in FILES}
        and mm.loader(binary, env, libs) == frozen["providers"],
        "build provenance",
    )
    plan, inputs, reference, gold, genuine = prepare(a, out, rec)
    mm.loader(reference, env, libs)
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
        caps=dict(memory_B=svc.CAP, stop_B=svc.STOP, wall_s=360, output_B=48 << 20, pack_B=8 << 30),
        full_model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
        energy_J=None,
    )
    (out / "raw").mkdir()
    rec["monitor_provider"], check_provider = svc.monitor_provider(prior)
    check_provider()
    guard, dynamic, bounded, group = svc.admit(a, prior, Q / "packed_real_layer", rec, out)
    mon = P["with_live_admission"](svc.Monitor, policy, window)(
        guard, dynamic, bounded, group, out / "monitor.jsonl", start, elapsed_limit=360
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "scope high")
    save(out / "provenance.json", rec)
    rows = {"exact": {}, "price": {}}
    monitor = threading.Thread(target=mon.run, daemon=True)
    monitor.start()
    try:
        rec["stage"] = "reference"
        refout = out / "MONO"
        invoke([reference, inputs, "MONO", "exact", refout], "reference", out, env, mon)
        independent = L["verify"](read(out / "reference.json"), genuine["exact"], gold, refout)
        rec["reference_sha256"] = sha(out / "reference.json")
        rec["service_pack_B"] = independent["returned_bytes"]
        for phase in rows:
            for case in CASES:
                rec["stage"] = phase + "-" + case
                invoke([binary, plan, case, phase], rec["stage"], out, env, mon)
                native = read(out / (rec["stage"] + ".json"))
                GR["validate_native"](native, case, phase)
                for k in ("logits", "biased", "ranks", "mix"):
                    need(
                        native["router"][k] == gold["input_sha256"][case + "/" + k],
                        "router hash " + k,
                    )
                if phase == "exact":
                    GR["exact_result"](native, case)
                rows[phase][case] = native
                rec["service_pack_B"] += native["pack_reads"] * GR["WINDOW"]
                need(rec["service_pack_B"] <= 8 << 30, "pack budget")
        decision = GR["grade"](rows["exact"], rows["price"])
        save(out / "decision.json", decision)
        rec["decision"] = decision["cost"]
    finally:
        mon.end.set()
        monitor.join(6)
        need(not monitor.is_alive(), "telemetry drain")
        mon.check()
        rec.update(
            samples=mon.count,
            monitor_sha256=sha(out / "monitor.jsonl"),
            final_cgroup=bounded.cgroup_state(),
        )
    check_provider()
    need(
        P["fd_stat"](Path(gold["pack_path"]).stat()) == gold["pack_stat"]
        and (group / "cgroup.procs").read_text().split() == [str(os.getpid())]
        and int((group / "memory.swap.peak").read_text()) == 0
        and prior.footprint(out) < 48 << 20,
        "clean shutdown, unchanged source or resource limit",
    )
    rec.update(
        status="MEASURED_ROUTED_CPU0",
        grade_sha256=sha(out / "decision.json"),
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=int((group / "memory.swap.peak").read_text()),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="mode", required=True)
    modes.add_parser("check").add_argument("evidence", type=Path)
    for mode in ("build", "physical"):
        sub = modes.add_parser(mode)
        for key in ("backend", "new-output-dir"):
            sub.add_argument("--" + key, type=Path, required=True)
        sub.add_argument("--commit", required=True)
        if mode == "physical":
            for key in ("build-dir", "archive-part", "manifest", "c55-receipt"):
                sub.add_argument("--" + key, type=Path, required=True)
            for key in ("build-sha256", "c55-sha256", "unit"):
                sub.add_argument("--" + key, required=True)
    a = p.parse_args()
    if a.mode == "check":
        dirs = [
            {c: read(a.evidence / (k + "-" + c + ".json")) for c in CASES}
            for k in ("exact", "price")
        ]
        decision = GR["grade"](*dirs)
        need(decision == read(a.evidence / "decision.json"), "published grading")
        print(decision["numerical"], decision["cost"])
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
    print(rec["status"], rec.get("reason", rec.get("decision", "")))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))


if __name__ == "__main__":
    main()
