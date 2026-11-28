"""Price the 13-hit CPU prefill group with two mandatory reads on the sealed worker binary."""

import argparse
import gzip
import json
import os
import threading
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
H = HERE.parents[1]
B = run_path(H / "run.py")
CORE, G, P, Q, mm, read, save, pin, sha, need = (
    B[k] for k in ("CORE", "G", "P", "Q", "mm", "read", "save", "pin", "sha", "need")
)
TAGS = ("P97", "P106")
CASE, REGIME = "prefill9", "BANK"
METHOD = "ce4fa59ff464ae944768747d5ee36d866031df85d049ca3cbe142b3cd90eeb7e"
ENTRY = "5e815f588d0aacb559346eeca693311222c2a61d7683b03ede140db275107598"
CONTROL = "3d9523bb9da37a508752ddbda6b5e8d44684488f70e2cf806dd1ecd11d542789"
BUILD = "d5e501bbc55f0398b35d7cbe1fd34df640abd96fa7d2d19229ccef9b4b5cdd07"


def scenarios():
    pin(HERE / "mixed-protocol.md", METHOD)
    v = read(pin(HERE / "evidence-entry-20261128-r01/decision.json", ENTRY))
    scenarios = read(
        pin(
            H / "evidence-20261128-r01/scenarios.json",
            "ab8cc2eaed4deeedd5c8956d8cb2db428193b072ee1bc9dfd7357e47e1bb9334",
        )
    )
    result = {}
    for tag in TAGS:
        case = scenarios[tag][CASE]
        record = v["journals"][tag]["registered"][CASE]
        need(record["site"] == case["site"] and len(record["expert"]) == 13, "continuous entry")
        for j in case["jobs"]:
            j["hit"] = j["expert"] in record["expert"]
        need(
            [j["expert"] for j in case["jobs"] if not j["hit"]] == [116, 50]
            and len(case["demands"]) == 18,
            "unpaid prefill miss",
        )
        result[tag] = case
    return result


def expected_reads(case):
    jobs = case["jobs"]
    boot = (
        {j["old"] for j in jobs}
        | {j["expert"] for j in jobs if j["hit"]}
        | {k[3] for k in case["entry"]}
    )
    misses = sum(not j["hit"] for j in jobs)
    # Each role occurs once in exact, once in warmup and fourteen times in paired blocks.
    return 2 * len(boot) + 16 * (len(jobs) + 3 * misses) + misses


def grade(samples):
    result, copy, one = {}, {}, {}
    total = 0
    for tag, case in scenarios().items():
        arm = G["summarize"](samples[tag], case, tag, CASE, REGIME)
        for d in arm["directions"]:
            idx = tag, d["direction"]
            pair = d["comparisons"]
            copy[idx] = pair["COPY_minus_ALL"]["median_ns"]
            one[idx] = pair["best_ONE_minus_ALL"]["median_ns"]
        need(
            arm["hits"] == 13
            and arm["graded_submissions"] == 56
            and arm["exact_warm_price_pack_B"] == G["WINDOW"] * expected_reads(case),
            "count or pack budget",
        )
        result[tag] = arm
        total += arm["exact_warm_price_pack_B"]
    status = "INCONCLUSIVE_GROUP_EXTENSION"
    if min(one.values()) > 0 and min(copy.values()) > 0:
        status = "GO_LOCAL_GROUP_EXTENSION"
    elif max(one.values()) < 0:
        status = "NO_GO_LOCAL_GROUP_EXTENSION"
    return dict(
        status=status,
        arms=result,
        pack_requested_B=total,
        graded_submissions=112,
        warmup_submissions=8,
        exact_submissions=10,
        protocol_sha256=METHOD,
        entry_sha256=ENTRY,
        evidence="MEASURED_COMPONENT_LAPTOP",
        model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
        integrated_product_gain_ns=None,
        M3="PARTIAL",
        M4="NOT_MET",
    )


def physical(a, out, rec, start):
    libs, env = B["authority"](a)
    frozen = read(pin(a.build_dir / "receipt.json", BUILD))
    exe = pin(a.build_dir / "group-service", frozen["elf"])
    need(
        frozen["sources"] == {n: sha(H / n) for n in B["SOURCES"]}
        and mm.loader(exe, env, libs) == frozen["providers"],
        "different worker build",
    )
    original = read(pin(a.source_plan, CONTROL))
    meta = read(pin(a.manifest / "receipt.json", P["MANIFEST_RECEIPT"]))
    record = read(H / "evidence-20261128-r01/physical.json")
    pack = Path(original["pack"])
    need(
        str(pack) == meta["pack_path"]
        and P["fd_stat"](pack.stat()) == meta["pack_stat"] == original["pack_stat"]
        and record["pack"] == meta["pack_sha256"] == P["PACK"]
        and record["model"] == meta["model_sha256"]
        and sha(a.manifest / "integral-index.json") == record["index"] == P["INDEX"],
        "source pack or index",
    )
    cases = scenarios()
    for tag, case in cases.items():
        original["scenarios"][tag][CASE] = case
    plan = out / "plan.json"
    save(plan, original)
    expected = G["WINDOW"] * sum(expected_reads(case) for case in cases.values())
    need(expected < 16 << 30, "prospective pack cap")
    prior, svc = P["shared"]()
    svc.WALL = 240
    a.checkout = B["ROOT"]
    c55 = read(pin(a.c55_receipt, a.c55_sha256))
    policy = read(
        pin(a.c55_receipt.parent / "resource-policy.json", c55["canonical_policy_sha256"])
    )
    window = run_path(Q / "nvme_admission/window.py")
    P["live_admission"](policy, window)
    rec.update(
        c55=a.c55_sha256,
        elf=frozen["elf"],
        build=BUILD,
        backend=mm.PIN,
        providers=frozen["providers"],
        host=os.uname().nodename,
        kernel=os.uname().release,
        cpu=c55["cpu"],
        gpu=c55["gpu_name"],
        driver=c55["gpu_driver"],
        power=c55["power"],
        disk=c55["model_device"],
        energy_J=None,
        protocol=METHOD,
        plan_sha256=sha(plan),
        source_plan=CONTROL,
        entry=ENTRY,
        program=sha(Path(__file__)),
        index=P["INDEX"],
        model=record["model"],
        pack=P["PACK"],
        expected_pack_B=expected,
        caps=dict(
            wall_s=240,
            memory_B=svc.CAP,
            stop_B=svc.STOP,
            swap_B=0,
            output_B=48 << 20,
            pack_B=16 << 30,
        ),
    )
    (out / "raw").mkdir()
    rec["monitor_provider"], provider = svc.monitor_provider(prior)
    provider()
    guard, dynamic, bounded, group = svc.admit(a, prior, Q / "packed_real_layer", rec, out)
    mon = P["with_live_admission"](svc.Monitor, policy, window)(
        guard, dynamic, bounded, group, out / "monitor.jsonl", start, elapsed_limit=240
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "scope high")
    save(out / "provenance.json", rec)
    monitor = threading.Thread(target=mon.run, daemon=True)
    monitor.start()
    samples = {tag: {} for tag in TAGS}
    try:
        for phase in ("exact", "price"):
            for tag in TAGS:
                stage = "-".join((tag, CASE, REGIME, phase))
                rec["stage"] = stage
                CORE["invoke"]([exe, plan, tag, CASE, REGIME, phase], stage, out, env, mon)
                data = read(out / (stage + ".json"))
                with (out / "raw" / (stage + ".jsonl")).open() as f:
                    need(
                        [json.loads(line) for line in f] == data["rows"],
                        "incomplete incremental journal",
                    )
                G["verify"](data, cases[tag], tag, CASE, REGIME, phase)
                samples[tag][phase] = data
        result = grade(samples)
        need(result["pack_requested_B"] == expected, "terminal pack count")
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
        "terminal scope",
    )
    rec.update(
        status="MEASURED_CONTINUOUS_PREFILL_GROUP",
        decision=result["status"],
        peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=0,
        gpu_compute=False,
        model_forwards=0,
        HTTP_requests=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="mode", required=True)
    modes.add_parser("check").add_argument("evidence", type=Path)
    sub = modes.add_parser("physical")
    for name in (
        "backend",
        "source-plan",
        "build-dir",
        "manifest",
        "new-output-dir",
        "c55-receipt",
    ):
        sub.add_argument("--" + name, type=Path, required=True)
    for name in ("commit", "unit", "c55-sha256"):
        sub.add_argument("--" + name, required=True)
    a = p.parse_args()
    if a.mode == "check":
        result = grade(json.loads(gzip.decompress((a.evidence / "samples.json.gz").read_bytes())))
        need(result == read(a.evidence / "decision.json"), "published mixed price")
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
        physical(a, out, rec, start)
    except Exception as e:
        rec.update(status="FAIL_PRESERVED", reason=repr(e))
    rec["elapsed_s"] = time.monotonic() - start
    save(out / ".pending", rec)
    (out / ".pending").rename(out / "receipt.json")
    print(rec["status"], rec.get("decision", rec.get("reason")))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))


if __name__ == "__main__":
    main()
