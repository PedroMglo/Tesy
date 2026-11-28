"""Measure four FIFO worker lanes after importing the preceding native availability."""

import argparse
import copy
import gzip
import json
import os
import subprocess
import threading
import time
from itertools import product
from pathlib import Path
from runpy import run_path
from statistics import median
from types import FunctionType

HERE = Path(__file__).resolve().parent
M = run_path(HERE / "mixed.py")
H, B, CORE, G, P, Q, mm, read, save, pin, sha, need = (
    M[k] for k in ("H", "B", "CORE", "G", "P", "Q", "mm", "read", "save", "pin", "sha", "need")
)
TAGS = ("P97", "P106")
ARMS = ("DISK", "COPY", "ONE_27", "ONE_63", "ALL")
METHOD = "701aee7b4907889690f0ef72e7ca34582d20f64ccc8cb9ad3935620ad55de3c0"
QUEUE = "63dfa92ab0043073ab13d1a2d11a62dda4e5907452880eada36aa540961989d9"
SOURCE = "41a568c392343d144c2222d7958c6cdb91de08b541db87a0f06b9ab9c81a8995"


def registered_roles(case, regime, scenario):
    need(
        case == "prefill9"
        and regime == "BANK"
        and {27, 63} <= {j["expert"] for j in scenario["jobs"] if j["hit"]},
        "single-expert controls",
    )
    return list(ARMS)


# Use the original, sealed verifier and summarizer for all weights, times and faults.
# Give them a private registry of the five roles without changing the historical module.
def registered(fn, **bindings):
    return FunctionType(fn.__code__, fn.__globals__ | bindings, fn.__name__)


C = G["C"] | {"role_names": registered_roles}
verify = registered(G["verify"], C=C)
summarize = registered(G["summarize"], C=C, verify=verify)


def source_scenarios():
    pin(HERE / "dispatch-protocol.md", METHOD)
    pin(H / "grade.py", "5da5f6749143de3ec0c288007dc888a36419952e07e19deef0cfb4787f46a00f")
    receipt = read(pin(HERE / "evidence-queue-20261128-r02/decision.json", QUEUE))
    need(receipt["status"] == "GO_FIFO_FIXTURE", "queue admission")
    fixed = M["scenarios"]()
    result = {}
    for tag in TAGS:
        state = receipt["journals"][tag]["prefill9"]["state"]
        for rule in ("FIXED", "FIFO"):
            case = copy.deepcopy(fixed[tag])
            prior = max(0, state["previous_dispatch_ns"])
            for j, s in zip(case["jobs"], state["jobs"], strict=True):
                w = j["worker"]
                need(
                    (j["index"], j["expert"], w, j["dispatch_ns"])
                    == (s["index"], s["expert"], s["worker"], s["dispatch_ns"])
                    and j["reserve_ns"] <= s["enqueue_ns"] <= j["dispatch_ns"],
                    "original claim",
                )
                j["reserve_ns"] = s["enqueue_ns"]
                prior = max(prior, j["reserve_ns"], state["carry_publish_ns"][w])
                if rule == "FIFO":
                    j["dispatch_ns"] = prior
            result[tag + "-" + rule] = case
    return result


def build(a, out, rec):
    libs, env = B["authority"](a)
    pin(HERE / "dispatch-protocol.md", METHOD)
    group = CORE["L"]["BUILD"]["cgroup"](2 << 30)
    original = pin(H / "service.cpp", SOURCE)
    source = original.read_text()
    before = '(name=="decode4" || j.at("expert")==63)'
    after = '(name=="decode4" || j.at("expert")==27 || j.at("expert")==63)'
    need(source.count(before) == 1, "ambiguous role list")
    unit = out / "service.cpp"
    unit.write_text(source.replace(before, after))
    baseline = read(pin(H / "evidence-20261128-r01/build.json", M["BUILD"]))
    cmd = baseline["command"].copy()
    need(
        cmd.count(str(original)) == 1
        and cmd[-2] == "-o"
        and sha(Path(cmd[0])) == baseline["compiler_sha256"]
        and sha(Path("/usr/lib64/libcrypto.so.3")) == baseline["crypto"],
        "original compiler and source",
    )
    pin(
        a.backend / "vendor/nlohmann/json.hpp",
        "aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63",
    )
    exe = out / "group-service"
    cmd[cmd.index(str(original))] = str(unit)
    cmd[-1] = str(exe)
    rec.update(
        command=cmd,
        original_source=SOURCE,
        compiled_source=sha(unit),
        program=sha(HERE / "dispatch.py"),
        compiler=baseline["compiler_sha256"],
        crypto=baseline["crypto"],
        original_build=M["BUILD"],
        method=METHOD,
    )
    save(out / "provenance.json", rec)
    with (out / "compile.log").open("xb") as f:
        subprocess.run(
            cmd, cwd=out, env=env, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=80
        )
    rec.update(
        status="BUILT_BOTH_SINGLE_CONTROLS",
        elf=sha(exe),
        providers=mm.loader(exe, env, libs),
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=int((group / "memory.swap.peak").read_text()),
    )


def grade(samples):
    cases = source_scenarios()
    need(set(samples) == set(cases), "incomplete dispatch family")
    results = {
        tag: summarize(samples[tag], case, tag, "prefill9", "BANK") for tag, case in cases.items()
    }
    contrasts = {}
    for tag, d in product(TAGS, range(2)):
        series = [
            results[tag + "-" + rule]["directions"][d]["comparisons"]["best_ONE_minus_ALL"]["ns"]
            for rule in ("FIXED", "FIFO")
        ]
        difference = [y - x for x, y in zip(*series, strict=True)]
        contrasts[tag + "-" + str(d)] = dict(
            fixed_ns=series[0],
            fifo_ns=series[1],
            difference_ns=difference,
            median_fifo_ns=median(series[1]),
            median_difference_ns=median(difference),
            positive_fifo=sum(v > 0 for v in series[1]),
            positive_difference=sum(v > 0 for v in difference),
        )
    local = [d["median_fifo_ns"] for d in contrasts.values()]
    extra = [d["median_difference_ns"] for d in contrasts.values()]
    status = (
        "GO_MEASURED_FIFO_GROUP"
        if min(local + extra) > 0
        else (
            "NO_GO_MEASURED_FIFO_GROUP" if max(local) <= 0 else "INCONCLUSIVE_MEASURED_FIFO_GROUP"
        )
    )
    return dict(
        status=status,
        conditions=results,
        contrasts=contrasts,
        method=METHOD,
        prior_queue=QUEUE,
        pack_requested_B=sum(r["exact_warm_price_pack_B"] for r in results.values()),
        graded_submissions=sum(r["graded_submissions"] for r in results.values()),
        warmup_submissions=20,
        exact_submissions=sum(r["exact_arms"] for r in results.values()),
        evidence="MEASURED_COMPONENT_LAPTOP",
        model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
        client_gain_ns=None,
        M3="PARTIAL",
        M4="NOT_MET",
    )


def physical(a, out, rec, start):
    libs, env = B["authority"](a)
    built = read(pin(a.build_dir / "receipt.json", a.build_sha256))
    exe = pin(a.build_dir / "group-service", built["elf"])
    need(
        built["commit"] == a.commit
        and built["status"] == "BUILT_BOTH_SINGLE_CONTROLS"
        and built["program"] == sha(HERE / "dispatch.py")
        and mm.loader(exe, env, libs) == built["providers"],
        "native build",
    )
    cases = source_scenarios()
    original = read(pin(a.source_plan, M["CONTROL"]))
    pack = Path(original["pack"])
    meta = read(pin(a.manifest / "receipt.json", P["MANIFEST_RECEIPT"]))
    need(
        str(pack) == meta["pack_path"]
        and P["fd_stat"](pack.stat()) == meta["pack_stat"] == original["pack_stat"]
        and P["PACK"] == meta["pack_sha256"]
        and sha(a.manifest / "integral-index.json") == P["INDEX"],
        "target data",
    )
    expected = (
        sum(
            2
            * len(
                {j["old"] for j in c["jobs"]}
                | {j["expert"] for j in c["jobs"] if j["hit"]}
                | {k[3] for k in c["entry"]}
            )
            + 16 * (15 + 4 * 2)
            + 2
            for c in cases.values()
        )
        * G["WINDOW"]
    )
    need(expected < 32 << 30, "read cap")
    plan = out / "plan.json"
    save(plan, original | dict(scenarios={k: {"prefill9": v} for k, v in cases.items()}))
    prior, svc = P["shared"]()
    svc.WALL = 300
    a.checkout = B["ROOT"]
    c55 = read(pin(a.c55_receipt, a.c55_sha256))
    policy = read(
        pin(a.c55_receipt.parent / "resource-policy.json", c55["canonical_policy_sha256"])
    )
    window = run_path(Q / "nvme_admission/window.py")
    P["live_admission"](policy, window)
    rec.update(
        c55=a.c55_sha256,
        build=a.build_sha256,
        elf=built["elf"],
        providers=built["providers"],
        program=sha(HERE / "dispatch.py"),
        host=os.uname().nodename,
        kernel=os.uname().release,
        cpu=c55["cpu"],
        gpu=c55["gpu_name"],
        driver=c55["gpu_driver"],
        power=c55["power"],
        disk=c55["model_device"],
        pack=P["PACK"],
        model=meta["model_sha256"],
        index=P["INDEX"],
        source_plan=M["CONTROL"],
        plan=sha(plan),
        expected_pack_B=expected,
        caps=dict(
            wall_s=300,
            memory_B=svc.CAP,
            stop_B=svc.STOP,
            swap_B=0,
            output_B=48 << 20,
            pack_B=32 << 30,
        ),
        energy_J=None,
    )
    (out / "raw").mkdir()
    rec["monitor_provider"], provider = svc.monitor_provider(prior)
    provider()
    guard, dynamic, bounded, group = svc.admit(a, prior, Q / "packed_real_layer", rec, out)
    mon = P["with_live_admission"](svc.Monitor, policy, window)(
        guard, dynamic, bounded, group, out / "monitor.jsonl", start, elapsed_limit=300
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "scope high")
    save(out / "provenance.json", rec)
    monitor = threading.Thread(target=mon.run, daemon=True)
    monitor.start()
    samples = {tag: {} for tag in cases}
    try:
        for phase in ("exact", "price"):
            for tag, case in cases.items():
                stage = tag + "-prefill9-BANK-" + phase
                rec["stage"] = stage
                CORE["invoke"]([exe, plan, tag, "prefill9", "BANK", phase], stage, out, env, mon)
                data = read(out / (stage + ".json"))
                with (out / "raw" / (stage + ".jsonl")).open() as f:
                    need(
                        [json.loads(line) for line in f] == data["rows"],
                        "incomplete incremental journal",
                    )
                verify(data, case, tag, "prefill9", "BANK", phase)
                samples[tag][phase] = data
        result = grade(samples)
        need(
            result["pack_requested_B"] == expected and result["graded_submissions"] == 280,
            "work conservation",
        )
        save(out / "decision.json", result)
        with (out / "samples.json.gz").open("xb") as f:
            f.write(
                gzip.compress(
                    json.dumps(samples, separators=(",", ":"), sort_keys=True).encode(), mtime=0
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
    provider()
    need(
        P["fd_stat"](pack.stat()) == meta["pack_stat"]
        and not int((group / "memory.swap.peak").read_text())
        and (group / "cgroup.procs").read_text().split() == [str(os.getpid())]
        and prior.footprint(out) < 48 << 20,
        "terminal state",
    )
    rec.update(
        status="MEASURED_FIFO_DISPATCH",
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
    for name in ("build", "physical"):
        sub = modes.add_parser(name)
        for k in ("backend", "new-output-dir"):
            sub.add_argument("--" + k, type=Path, required=True)
        sub.add_argument("--commit", required=True)
        if name == "physical":
            for k in ("source-plan", "build-dir", "manifest", "c55-receipt"):
                sub.add_argument("--" + k, type=Path, required=True)
            for k in ("build-sha256", "unit", "c55-sha256"):
                sub.add_argument("--" + k, required=True)
    a = p.parse_args()
    if a.mode == "check":
        result = grade(json.loads(gzip.decompress((a.evidence / "samples.json.gz").read_bytes())))
        need(result == read(a.evidence / "decision.json"), "published evaluation")
        print(result["status"], result["graded_submissions"], result["pack_requested_B"])
        return
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    start = time.monotonic()
    rec = dict(
        status="FAIL_PRESERVED", commit=a.commit, tree=mm.git(B["ROOT"], "rev-parse", "HEAD^{tree}")
    )
    try:
        if a.mode == "build":
            build(a, out, rec)
        else:
            physical(a, out, rec, start)
    except Exception as exc:
        rec.update(status="FAIL_PRESERVED", reason=repr(exc))
    rec["elapsed_s"] = time.monotonic() - start
    save(out / ".pending", rec)
    (out / ".pending").rename(out / "receipt.json")
    print(rec["status"], rec.get("decision", rec.get("reason")))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))


if __name__ == "__main__":
    main()
