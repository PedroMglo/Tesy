"""Verify the actual C266 CPU tile under an externally created, exclusive C118 scope."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import threading
import time
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q = HERE.parents[1]
MODES = ("ORIGINAL", "OFF", "MMID", "FUSION")
CANDIDATE = "526a4684edd7eb0e60fb16dabb99d23198f9ede8822ef716c480b5e853c3a208"
NUMERIC = "c7926f18eb558240f3d14a2be2ed12872de98b2fbfbf5ed6b57b51d9140960bc"
ORIGINAL_BUILD = "37f7ceec65cab37640dbf4b5b1f48bec19165d097a84adbfb956a01ea7db1f13"
MMID = "4af89ce9e9957cb20095df364f051c3fed3960f8ce5a7fe4c63cfab248c61df8"
PASS = "PASS_PARKED_FUSION_REAL_TILE"
COUNTER = (
    "counter_pid",
    "counter_present",
    "counter_provider",
    "counter_before",
    "counter_after",
    "counter_delta",
)
ROW_BYTES = 368640


def need(value, reason):
    if not value:
        raise ValueError(reason)


def modules():
    path = Q / "parked_mmid/profile.py"
    need(hashlib.sha256(path.read_bytes()).hexdigest() == MMID, "parked MMID supervisor")
    spec = importlib.util.spec_from_file_location("fusion_mmid", path)
    mm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mm)
    c = mm.cpu0_module()
    prior = c.module(Q / "packed_real_layer/profile.py", "fusion_layer", c.LAYER)
    svc = c.module(Q / "packed_layer_service/profile.py", "fusion_service", c.SERVICE)
    return mm, c, prior, svc


def diff(gold, found):
    need(len(found) == len(gold) == ROW_BYTES, "FFN row count")
    for i, (a, b) in enumerate(
        zip(struct.iter_unpack("<I", gold), struct.iter_unpack("<I", found), strict=True)
    ):
        if a != b:
            return dict(
                f32_index=i,
                expected_bits=a[0],
                observed_bits=b[0],
                nonfinite=(b[0] & 0x7F800000) == 0x7F800000,
            )
    return None


def finiteness(data):
    count = 0
    first = None
    for i, (bits,) in enumerate(struct.iter_unpack("<I", data)):
        if bits & 0x7F800000 == 0x7F800000:
            if first is None:
                first = {"f32_index": i, "observed_bits": bits}
            count += 1
    return {"nonfinite_count": count, "first_nonfinite": first}


def counter_gate(mode, marker, pid, providers, sha):
    need(set(marker["providers"]) == set(providers), "provider identities")
    for role, (path, digest) in providers.items():
        real = Path(marker["providers"][role])
        need(
            real.is_absolute() and real.samefile(path) and sha(real) == digest,
            "runtime provider:" + role,
        )
    need(type(marker["counter_pid"]) is int and marker["counter_pid"] == pid > 0, "counter process")
    present = mode != "ORIGINAL"
    need(mode in MODES and marker["counter_present"] is present, "counter availability")
    if not present:
        need(all(marker[n] is None for n in COUNTER[2:]), "original reported a counter")
        return None
    provider = Path(marker["counter_provider"])
    need(
        provider.is_absolute() and provider.samefile(providers["cpu"][0]), "counter from wrong DSO"
    )
    before, after, delta = (marker[k] for k in COUNTER[3:])
    need(
        all(type(v) is int and v >= 0 for v in (before, after, delta))
        and before == 0
        and after - before == delta,
        "counter endpoints",
    )
    return delta


def after_join(row, marker):
    need(all(row[k] == marker[k] for k in (*COUNTER, "providers")), "provider reports disagree")
    need(
        row["counter_after_join_verified"] is True
        and type(row["counter_after_graph"]) is type(marker["counter_after"])
        and row["counter_after_graph"] == marker["counter_after"],
        "counter changed across join",
    )


def verdict(mode, delta, mismatch):
    if mismatch:
        return "INCONCLUSIVE_ORIGINAL_GOLD" if mode == "ORIGINAL" else "NO_GO_EXACTNESS"
    if mode == "FUSION" and delta != 7:
        return "INCONCLUSIVE_NOT_APPLIED" if delta == 0 else "INCONCLUSIVE_REGION_COUNT"
    if mode in ("OFF", "MMID") and delta != 0:
        return "INCONCLUSIVE_ABLATION_COUNT"
    return None


def family(a, r, control, start):
    mm, c, prior, svc = control
    need(a.checkout == Q.parents[1] and HERE == a.checkout / a.study, "checkout")
    git = ["/usr/bin/git", "--no-optional-locks", "-C", a.checkout]
    need(
        re.fullmatch("[0-9a-f]{40}", a.expect_head)
        and prior.command([*git, "rev-parse", "HEAD"]) == a.expect_head
        and not prior.command([*git, "status", "--porcelain"]),
        "clean frozen checkout",
    )
    num = prior.sealed_json(a.numerical_dir / "receipt.json", NUMERIC)
    need(
        num["status"] == "PASS_PARKED_FUSION_NUMERICAL_FAMILY"
        and num["decision"] == "GO_REAL_TILE"
        and num["candidate_cpu_sha256"] == CANDIDATE
        and [num["arms"][m.lower()]["fusion_count"] for m in MODES] == [0, 0, 0, 18],
        "synthetic gate",
    )
    ref = prior.sealed_json(Q / "cpu0_suffix/physical-r01/receipt.json", mm.REFERENCE)
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C291_FUSION_COUNTER_CLIENT_BUILD"
        and build["libs"] == prior.LIBS
        and build["worker_commit"] == c.WORKER
        and build["worker_tree"] == c.TREE
        and build["original_build_sha256"] == ORIGINAL_BUILD
        and set(build["sources"]) == {"build.py", "observer.patch"},
        "reader build",
    )
    for commit in (num["commit"], build["commit"]):
        need(re.fullmatch("[a-f0-9]{40}", commit), "build commit")
        subprocess.run(
            [*git, "merge-base", "--is-ancestor", commit, a.expect_head], check=True, timeout=8
        )
    for path, digest in build["sources"].items():
        need(
            svc.frozen(a.checkout, HERE / path, build["commit"]) == digest
            and svc.frozen(a.checkout, HERE / path, a.expect_head) == digest,
            "client source",
        )
    exe = a.build_dir / "suffix-layer"
    prior.sealed_file(exe, build["binary_sha256"])
    # Reuse the C269 loader isolation. The numerical DSO lives in its original sealed build.
    search = Namespace(**(vars(a) | {"build_dir": a.numerical_dir}))
    environments = {}
    for mode in MODES:
        single = {"ORIGINAL": "ORIGINAL", "OFF": "OFF", "MMID": "ON", "FUSION": "ON"}[mode]
        env, providers = mm.settings(search, prior, ref, num, single)
        if mode != "ORIGINAL":
            env["TESY_CPU_PARKED_FUSION"] = str(int(mode == "FUSION"))
        lines = prior.command(["/usr/bin/ldd", exe], env)
        need(
            "not found" not in lines and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", lines),
            "non-CPU dependency",
        )
        paths = [
            Path(line.split()[2]).resolve(strict=True)
            for line in lines.splitlines()
            if line.strip().startswith("libggml") and " => " in line
        ]
        need(
            len(paths) == len(providers)
            and set(paths) == {p.resolve() for p, _ in providers.values()},
            "resolved GGML providers",
        )
        environments[mode] = (env, providers)
    r.update(
        commit=a.expect_head,
        tree=prior.command([*git, "rev-parse", "HEAD^{tree}"]),
        source_sha256={
            k: svc.frozen(a.checkout, HERE / k, a.expect_head)
            for k in ("protocol.md", "profile.py")
        },
        build_sha256=a.build_sha256,
        executable_sha256=build["binary_sha256"],
        numerical_receipt_sha256=NUMERIC,
        candidate_cpu_sha256=CANDIDATE,
        reference_sha256=mm.REFERENCE,
        parent_profile_sha256=MMID,
    )
    _, files = svc.inputs(a, prior, r)
    with (a.input_dir / "ffn_moe_out-0.bin").open("rb") as f:
        f.seek(ROW_BYTES)
        gold = f.read(ROW_BYTES)
    need(hashlib.sha256(gold).hexdigest() == c.GOLD, "C266 gold")
    r["monitor_provider"], unchanged = svc.monitor_provider(prior)
    out = a.new_output_dir
    (out / "raw").mkdir()
    guard, policy, bounded, cg = svc.admit(a, prior, Q / "parked_mmid", r, out)
    mon = svc.Monitor(guard, policy, bounded, cg, out / "raw/samples.jsonl", start)
    thread = threading.Thread(target=mon.run, daemon=True)
    thread.start()
    try:
        for i, mode in enumerate(MODES):
            unchanged()
            need(files == {p.name: prior.token(p) for p in a.input_dir.iterdir()}, "input changed")
            prior.sealed_file(exe, build["binary_sha256"])
            for path, digest in environments[mode][1].values():
                prior.sealed_file(path, digest)
            decision = arm(a, mode, i, r, mon, control, ref, exe, environments[mode], gold)
            if decision:
                r["decision"] = decision
                break
        unchanged()
        need(
            files == {p.name: prior.token(p) for p in a.input_dir.iterdir()}
            and prior.sha(a.input_dir / "pack.bin") == r["pack_sha256"],
            "input closure",
        )
    finally:
        mon.end.set()
        thread.join(timeout=6)
        need(not thread.is_alive(), "monitor cleanup")
        r.update(
            monitor_samples=mon.count,
            monitor_sha256=prior.sha(mon.raw) if mon.raw.is_file() else None,
            peak_bytes=int((cg / "memory.peak").read_text()),
            swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
            cgroup_final=bounded.cgroup_state(),
            io_stat=(cg / "io.stat").read_text(),
            child_processes_at_cleanup=len((cg / "cgroup.procs").read_text().split()) - 1,
        )
        mon.check()
        need((cg / "cgroup.procs").read_text().split() == [str(os.getpid())], "unreaped child")
    need(
        mon.count >= 2 and prior.footprint(out) + 65536 + 3 * len(json.dumps(r)) < 32 * c.MIB,
        "output/telemetry",
    )
    successes = [row for row in r["arms"] if row["status"] == "PASS_TILE"]
    r.update(
        complete_work_arms=len(successes),
        expected_aligned_service_bytes=sum(row["expected_pread_bytes"] for row in successes),
        total_output_bytes=sum(row.get("tile_bytes", 0) for row in r["arms"]),
    )
    if "decision" not in r:
        need(
            len(successes) == 4
            and r["expected_aligned_service_bytes"] == 264437760
            and r["total_output_bytes"] == 4 * ROW_BYTES,
            "family conservation",
        )
        r["decision"] = "GO_TIMING_FIXTURE"
    r["status"] = PASS


def arm(a, mode, i, r, mon, control, ref, exe, runtime, gold):
    mm, c, prior, svc = control
    env, providers = runtime
    out = a.new_output_dir / f"{i:02d}-{mode}"
    out.mkdir()
    native = out / "native"
    rec = dict(
        mode=mode,
        run_index=i,
        status="FAIL_PRESERVED",
        child_started=False,
        started_utc=svc.clock(),
        kernel_env={
            k: env.get(k)
            for k in ("TESY_CPU_SUFFIX", "TESY_CPU_MMX_ALL_PARKED", "TESY_CPU_PARKED_FUSION")
        },
    )
    r["arms"].append(rec)
    proc = None
    try:
        mon.check()
        if i == 0:
            age = (
                dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(r["c118"]["last_utc"])
            ).total_seconds()
            need(0 <= age <= 3, "stale C118")
        start = time.monotonic()
        with (out / "stdout").open("xb") as so, (out / "stderr").open("xb") as se:
            proc = subprocess.Popen(
                [exe, a.input_dir, "OFF", native],
                cwd=a.checkout,
                env=env,
                stdout=so,
                stderr=se,
                start_new_session=True,
            )
            rec.update(pid=proc.pid, child_started=True)
            while proc.poll() is None:
                mon.check()
                need(
                    time.monotonic() - start < 180
                    and prior.footprint(a.new_output_dir) < 32 * c.MIB,
                    "child budget",
                )
                try:
                    proc.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    pass
        mon.check()
        rec.update(returncode=proc.returncode, spawn_to_observed_exit_s=time.monotonic() - start)
        need(rec["spawn_to_observed_exit_s"] < 180, "child time")
        err = (out / "stderr").read_text()
        labels = [
            line.removeprefix("PARKED_PROVIDERS ")
            for line in err.splitlines()
            if line.startswith("PARKED_PROVIDERS ")
        ]
        need(len(labels) == 1, "missing post-FFN provider receipt")
        marker = json.loads(labels[0])
        delta = counter_gate(mode, marker, proc.pid, providers, prior.sha)
        rec.update(
            {k: marker[k] for k in COUNTER},
            provider_sha256={k: h for k, (_, h) in providers.items()},
        )
        path = native / "tile.f32"
        need(not path.is_symlink() and path.stat().st_size == ROW_BYTES, "incomplete tile")
        bits = path.read_bytes()
        rec.update(finiteness(bits))
        first = diff(gold, bits)
        rec.update(
            tile_bytes=len(bits),
            tile_sha256=hashlib.sha256(bits).hexdigest(),
            first_difference=first,
        )
        decision = verdict(mode, delta, first)
        if first:
            need(
                rec["nonfinite_count"] == 0
                and proc.returncode == 1
                and "FAIL_C291_CPU0_TILE full FFN tile" in err,
                "numerical failure not qualified",
            )
            rec["status"] = "MISMATCH_IDENTIFIED"
            return decision
        need(proc.returncode == 0, "native exit")
        row = json.loads((out / "stdout").read_bytes())
        after_join(row, marker)
        rec.update(counter_after_graph=row["counter_after_graph"], counter_after_join_verified=True)
        fields = mm.native_row(prior, c, ref, row, providers, native, gold)
        # The existing harness has clocks; this protocol has no timing estimand.
        rec.update(
            {
                k: v
                for k, v in fields.items()
                if k not in {"graph_ns", "suffix_ns", "start_ns", "end_ns", "return_ns"}
            }
        )
        rec["status"] = "PASS_TILE"
        return decision
    finally:
        if proc is not None:
            mon.bounded.stop_own_group(proc)
            rec["returncode"] = proc.returncode
        for name in ("stdout", "stderr"):
            if (out / name).is_file():
                rec[name + "_sha256"] = prior.sha(out / name)
        rec["closed_utc"] = svc.clock()
        prior.put(out / "receipt.json", rec)


def main(a):
    os.umask(0o077)
    need(re.fullmatch("tesy-[a-z0-9][a-z0-9-]{1,110}", a.unit), "unit")
    a.study = str(HERE.relative_to(a.checkout))
    dest = a.new_output_dir
    dest.mkdir(mode=0o700)
    control = modules()
    _, c, prior, svc = control
    r = dict(
        status="FAIL_PRESERVED",
        unit=a.unit,
        started_utc=svc.clock(),
        arms=[],
        cap_bytes=c.CAP,
        stop_bytes=c.STOP,
        swap_max_bytes=0,
    )
    start = time.monotonic()
    try:
        family(a, r, control, start)
    except Exception as error:
        r.update(
            status="FAIL_PRESERVED",
            decision="INCONCLUSIVE",
            reason=f"{type(error).__name__}: {error}",
        )
    finally:
        r.update(
            elapsed_s=time.monotonic() - start,
            closed_utc=svc.clock(),
            supervisor_sha256=prior.sha(Path(__file__)),
        )
        prior.put(dest / "receipt.json", r)
    print(r["status"], r["decision"], flush=True)
    return int(r["status"] != PASS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "checkout",
        "build-dir",
        "numerical-dir",
        "libs",
        "input-dir",
        "c55-receipt",
        "new-output-dir",
    ):
        parser.add_argument("--" + key, type=lambda x: Path(x).resolve(), required=True)
    for key in ("expect-head", "build-sha256", "input-sha256", "c55-sha256", "unit"):
        parser.add_argument("--" + key, required=True)
    raise SystemExit(main(parser.parse_args()))
