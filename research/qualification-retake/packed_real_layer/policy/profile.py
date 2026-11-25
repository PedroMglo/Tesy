"""Admit and verify R0/BACKED/MUTANT real CPU0 tiles charged to one bounded family."""

import argparse
import hashlib
import json
import math
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q, ROOT = HERE.parents[1], HERE.parents[3]
CRYPTO = "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72"
MODES = ("R0", "BACKED", "MUTANT")
WALL, CHILD = 850, 240
MIB = 2**20
CAP, STOP, MAX_OUT = 4096 * MIB, 3584 * MIB, 16 * MIB
SLAB, STRIDE, TRANSFER = 4406400, 13258752, 13221888
ACTUAL = (45, 49, 57, 60, 98)
KEYS = tuple(range(40)) + ACTUAL
ROLES = ("gate", "down", "up")
PREP = "a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269"
MANIFEST_RECEIPT = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
INDEX = "63b7a76c7063e51944ee8a6296aea43109a336330b3657ffa357cddb44b59813"
MANIFEST = "f9773869e644f536bf465873ef0c72992af43296171ea959f9379f23afb57565"
PLACED = "adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000"
PACK = "f17e9fbf6f6aed1ad60ca7da3431c5156a946d2e0bf119722afc1f934cbc6b11"
GOLD = "bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24"
SHARED = {
    "cpu0_suffix/profile.py": "64c526583837b485564003eb92f398117e99dcd9f5304788aa0a4d1bebb2745e",
    "packed_layer_service/profile.py": (
        "ae3e5a752d68ad0187eba0e9329e1e03fcb9e429fe5367c6f5a4258e626cf7bb"
    ),
    "packed_real_layer/profile.py": (
        "3dfc12a50909fddd285143023a2edff5cd6e25b087453f21d4950649618db7cb"
    ),
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def shared():
    for name, digest in SHARED.items():
        need(hashlib.sha256((Q / name).read_bytes()).hexdigest() == digest, "shared helper " + name)
    load = run_path(Q / "cpu0_suffix/profile.py")["module"]
    prior = load(Q / "packed_real_layer/profile.py", "policy_prior")
    service = load(Q / "packed_layer_service/profile.py", "policy_monitor")
    service.WALL = WALL
    return prior, service


def fd_stat(stat):
    return dict(
        dev=stat.st_dev,
        inode=stat.st_ino,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        ctime_ns=stat.st_ctime_ns,
    )


def records(index, prepared):
    need(
        index["schema"] == "tesy-expert-local-integral-store-v1"
        and (index["stride"], index["weight_window"]) == (STRIDE, TRANSFER)
        and len(index["experts"]) == 4608,
        "integral geometry",
    )
    selected = {}
    for item in index["experts"]:
        e = item["expert"]
        if item["layer"] != 0 or e not in KEYS:
            continue
        check = index["experts"][e]
        need(
            item == check
            and e not in selected
            and item["tier"] == "CPU"
            and item["pack_offset"] == e * STRIDE,
            "CPU0 record identity",
        )
        roles = item["components"]
        need(
            len(roles) == 6
            and all(
                c["name"] == f"blk.0.ffn_{role}_exps.weight"
                and c["size_bytes"] == SLAB
                and c["packed_relative_offset"] == i * SLAB
                and c["type"] == "mxfp4"
                and re.fullmatch("[0-9a-f]{64}", c["sha256"])
                for i, (c, role) in enumerate(zip(roles[:3], ROLES, strict=True))
            ),
            "three weight spans",
        )
        if e in ACTUAL:
            need(roles == prepared["components"][str(e)], "historical tile components")
        selected[e] = [c["sha256"] for c in roles[:3]]
    need(set(selected) == set(KEYS), "45 real keys")
    return selected


def manifest(a, prior, prep):
    root = a.manifest_dir
    meta = prior.sealed_json(root / "receipt.json", MANIFEST_RECEIPT)
    runtime = prior.sealed_json(root / "expert-store-runtime.json", MANIFEST)
    idxfile = root / "integral-index.json"
    index = prior.sealed_json(idxfile, INDEX)
    need(
        meta["status"] == "PASS_DERIVED_C290_NVME_METADATA"
        and meta["pack_placement_sha256"] == PLACED
        and meta["index_sha256"] == runtime["index_sha256"] == INDEX
        and meta["manifest_sha256"] == MANIFEST
        and meta["model_sha256"] == prior.MODEL
        and Path(runtime["index_path"]) == idxfile
        and meta["pack_sha256"]
        == index["pack_sha256_write_stream"]
        == runtime["pack_sha256_write_stream"]
        == PACK
        and meta["pack_stat"] == runtime["pack_stat"]
        and index["pack_bytes"] == runtime["pack_bytes"] == 61096329216,
        "relocated manifest authority",
    )
    prior.sealed_file(root / "native-bases.tsv", meta["bases_sha256"])
    pack = Path(meta["pack_path"])
    need(
        pack == pack.resolve(strict=True) == Path(index["pack_path"])
        and fd_stat(pack.stat()) == meta["pack_stat"]
        and fd_stat(idxfile.stat()) == meta["index_stat"]
        and fd_stat((root / "expert-store-runtime.json").stat()) == meta["manifest_stat"],
        "placed file identities",
    )
    return pack, meta, records(index, prep)


def loader(a, prior, exe):
    env = prior.child_env(a, "DENSE")
    need(env["CUDA_VISIBLE_DEVICES"] == "" and env["OMP_NUM_THREADS"] == "8", "native environment")
    listed = prior.command(["/usr/bin/ldd", exe], env)
    need(
        "not found" not in listed and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", listed),
        "CPU only ELF",
    )
    ggml = {}
    crypto = None
    for line in listed.splitlines():
        words = line.split()
        if words and words[0] == "libcrypto.so.3":
            crypto = Path(words[2]).resolve(strict=True)
            prior.sealed_file(crypto, CRYPTO)
        if words and words[0].startswith("libggml"):
            p = Path(words[2]).resolve(strict=True)
            need(
                words[1] == "=>" and p.name in prior.LIBS and p.samefile(a.libs / p.name),
                "GGML loader",
            )
            prior.sealed_file(p, prior.LIBS[p.name])
            ggml[p.name] = prior.LIBS[p.name]
    need(
        ggml == prior.LIBS and crypto == Path("/usr/lib64/libcrypto.so.3").resolve(strict=True),
        "CPU GGML and OpenSSL closure",
    )
    return env


def measured_tile(path, gold):
    need(
        path.is_file() and not path.is_symlink() and path.stat().st_size == len(gold) == 368640,
        "complete tile",
    )
    raw = path.read_bytes()
    finite = all(math.isfinite(v) for (v,) in struct.iter_unpack("<f", raw))
    diff = sum(
        x != y
        for x, y in zip(struct.iter_unpack("<I", gold), struct.iter_unpack("<I", raw), strict=True)
    )
    return {
        "finite": finite,
        "bytes": len(raw),
        "values": len(raw) // 4,
        "changed_f32_bit_patterns": diff,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def vector(path, gold, mode):
    value = measured_tile(path, gold)
    need(value["finite"], "nonfinite tile")
    need((value["changed_f32_bit_patterns"] > 0) == (mode == "MUTANT"), "tile control")
    return value


def authority(a, prior, svc):
    git = ["/usr/bin/git", "--no-optional-locks", "-C", ROOT]
    need(
        re.fullmatch("[0-9a-f]{40}", a.commit)
        and prior.command([*git, "rev-parse", "HEAD"]) == a.commit
        and not prior.command([*git, "status", "--porcelain"]),
        "clean measurement revision",
    )
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        re.fullmatch("[0-9a-f]{40}", build["commit"])
        and build["libs"] == prior.LIBS
        and build["worker_commit"] == "c89c88b342054223e3f27a17fbfd0954803147ac"
        and build["worker_tree"] == "3962daa588dfa89971c60c95ce4c5054bc27fd3f",
        "pinned real worker",
    )
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", build["commit"], a.commit], check=True, timeout=8
    )
    frozen = {p: svc.frozen(ROOT, HERE / p, a.commit) for p in ("profile.py", "protocol.md")}
    need(
        build["status"] == "PASS_C291_CPU0_POLICY_BUILD"
        and set(build["executables"]) == {"policy-layer"}
        and build["crypto_sha256"] == CRYPTO
        and set(build["native_sources"])
        == {"build.py", "policy.patch", "policy_state.h", "policy_observe.h"},
        "build closure",
    )
    for p, s in build["native_sources"].items():
        need(
            Path(p).name == p
            and svc.frozen(ROOT, HERE / p, build["commit"])
            == s
            == svc.frozen(ROOT, HERE / p, a.commit),
            "native build source " + p,
        )
    exe = a.build_dir / "policy-layer"
    prior.sealed_file(exe, build["executables"]["policy-layer"])
    return (
        build,
        exe,
        loader(a, prior, exe),
        frozen,
        prior.command([*git, "rev-parse", "HEAD^{tree}"]),
    )


def verify_arm(row, mode, expected, pack_id, prior, libs):
    mutant = mode == "MUTANT"
    required = dict(
        status="PASS_C291_CPU0_DETECTED_MUTATION" if mutant else "PASS_C291_CPU0_POLICY_TILE",
        arm=mode,
        backing_enabled=mode != "R0",
        bias_nodes_observed=24,
        router_positions=153,
        ffn_positions=32,
        full_ffn_values=92160,
        graph_waves=8,
        active_waves=1,
        mmid_nodes_observed=24,
        compute_backend="CPU",
        workers_before_destructor=4,
        joined_workers=4,
        manager_destructor_returned=True,
        unique_loads=45,
        pread_bytes=594984960,
        logical_weight_bytes=594864000,
        weight_sets=135,
        seed_roles_verified=120,
        backing_roles_verified=15,
        backing_bytes=66096000,
        backing_experts=list(range(35, 40)),
        selected_weight_roles=15,
        selected_bias_roles=15,
        evicted_experts=list(range(5) if mode == "R0" else range(35, 40)),
        weight_mismatches=[[45, "gate"], [49, "gate"]] if mutant else [],
        fd_odirect=True,
        fd_stat=dict(
            dev=pack_id["dev"],
            ino=pack_id["inode"],
            size=pack_id["size_bytes"],
            mtime_ns=pack_id["mtime_ns"],
            ctime_ns=pack_id["ctime_ns"],
        ),
    )
    for k, v in required.items():
        need(type(row.get(k)) is type(v) and row[k] == v, "native witness: " + k)
    binds = row["selected_bindings"]
    need(
        isinstance(binds, list)
        and len(binds) == 5
        and all(
            isinstance(v, list) and len(v) == 3 and all(type(i) is int for i in v) for v in binds
        )
        and tuple(x[0] for x in binds) == ACTUAL
        and {x[1] for x in binds} == set(required["evicted_experts"])
        and all(x[2] == 2 and len(expected[x[0]]) == 3 for x in binds),
        "actual relocated bindings",
    )
    need(
        type(row["ffn_unequal"]) is int
        and (row["ffn_unequal"] > 0 if mutant else row["ffn_unequal"] == 0),
        "native FFN mismatch detector",
    )
    providers = row["providers"]
    need(set(providers) == {"cpu", "base", "crypto"}, "provider coverage")
    for kind, soname in prior.LIB_CODES.items():
        path = Path(providers[kind])
        need(
            path.is_absolute()
            and path.samefile(libs / soname)
            and prior.sha(path) == prior.LIBS[soname],
            "provider: " + kind,
        )
    crypto = Path(providers["crypto"])
    need(
        crypto.is_absolute()
        and crypto.samefile("/usr/lib64/libcrypto.so.3")
        and prior.sha(crypto) == CRYPTO,
        "in-process crypto provider",
    )
    return {k: row[k] for k in (*required, "selected_bindings", "ffn_unequal")}


def collect_child(a, prior, monitor, r, mode, exe, env, gold, expected, pack_id):
    folder = a.new_output_dir / mode
    folder.mkdir()
    native = folder / "native"
    row = {
        "mode": mode,
        "child_started": False,
        "started_utc": prior.now(),
        "status": "FAIL_PRESERVED",
    }
    r["arms"].append(row)
    child = None
    tic = time.monotonic()
    try:
        if mode == "R0":
            age = (
                datetime.now(UTC) - datetime.fromisoformat(r["c118"]["last_utc"])
            ).total_seconds()
            need(0 <= age <= 3, "expired C118 before first model-free arm")
        monitor.check()
        with (folder / "stdout").open("xb") as so, (folder / "stderr").open("xb") as se:
            child = subprocess.Popen(
                [exe, a.input_dir, mode, native, a.manifest_dir],
                env=env,
                cwd=ROOT,
                stdout=so,
                stderr=se,
                start_new_session=True,
            )
            row.update(pid=child.pid, child_started=True)
            while child.poll() is None:
                monitor.check()
                need(
                    time.monotonic() - tic < CHILD
                    and prior.footprint(a.new_output_dir) + 65536 < MAX_OUT,
                    "child time or output",
                )
                try:
                    child.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    pass
        row.update(rc=child.returncode, observed_child_s=time.monotonic() - tic)
        if child.returncode != 0 and (native / "tile.f32").is_file():
            row["terminal_tile_observation"] = measured_tile(native / "tile.f32", gold)
        need(child.returncode == 0 and row["observed_child_s"] <= CHILD, "native exit/time")
        result = json.loads((folder / "stdout").read_bytes())
        need({p.name for p in native.iterdir()} == {"tile.f32"}, "native file accounting")
        row["tile"] = vector(native / "tile.f32", gold, mode)
        row["proof"] = verify_arm(result, mode, expected, pack_id, prior, a.libs)
        need(
            row["tile"]["changed_f32_bit_patterns"] == row["proof"]["ffn_unequal"],
            "native mismatch count versus bitwise comparison",
        )
        monitor.check()
        row["status"] = result["status"]
    finally:
        if child is not None:
            monitor.bounded.stop_own_group(child)
            row["rc"] = child.returncode
        for name in ("stderr", "stdout"):
            if (folder / name).is_file():
                row[name + "_sha256"] = prior.sha(folder / name)
        row["closed_utc"] = prior.now()
        prior.put(folder / "receipt.json", row)


def run(a, r):
    prior, svc = shared()
    sys.path.insert(0, str(ROOT / "tools"))
    import run_bounded as bounded

    cg0 = bounded.cgroup_state()
    need(
        cg0
        and cg0["path"].endswith("/" + a.unit + ".scope")
        and cg0["memory_max"] == cg0["memory_high"] == CAP
        and cg0["swap_max"] == cg0["swap_current"] == 0
        and cg0["memory_peak"] < STOP,
        "4 GiB/zero swap dedicated scope",
    )
    build, exe, env, frozen, tree = authority(a, prior, svc)
    r.update(
        commit=a.commit,
        tree=tree,
        build_sha256=a.build_sha256,
        binary_sha256=build["executables"]["policy-layer"],
        sources=frozen,
        derived_manifest_receipt_sha256=MANIFEST_RECEIPT,
    )
    a.checkout = ROOT
    a.input_sha256 = PREP
    a.study = "research/qualification-retake/packed_real_layer/policy"
    prep, input_state = svc.inputs(a, prior, r)
    with (a.input_dir / "ffn_moe_out-0.bin").open("rb") as f:
        f.seek(368640)
        gold = f.read(368640)
    need(hashlib.sha256(gold).hexdigest() == GOLD, "CPU0 gold")
    pack, meta, expected = manifest(a, prior, prep)
    pack_id = meta["pack_stat"]
    metainputs = {p: prior.token(p) for p in a.manifest_dir.iterdir()}
    r.update(
        pack_stat=pack_id,
        integral_pack_sha256=PACK,
        selected_expert_count=len(expected),
        selected_components_sha256=hashlib.sha256(
            json.dumps(sorted(expected.items()), separators=(",", ":")).encode()
        ).hexdigest(),
    )
    r["monitor_provider"], check_provider = svc.monitor_provider(prior)
    (a.new_output_dir / "raw").mkdir()
    with pack.open("rb", buffering=0) as fd:

        def recheck():
            need(
                fd_stat(os.fstat(fd.fileno())) == fd_stat(pack.stat()) == pack_id
                and metainputs == {p: prior.token(p) for p in a.manifest_dir.iterdir()}
                and input_state == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
                "input mutated",
            )
            prior.sealed_file(exe, build["executables"]["policy-layer"])
            check_provider()

        recheck()
        window = run_path(Q / "nvme_admission/window.py")
        gate = prior.sealed_json(a.c55_receipt, a.c55_sha256)
        pol = prior.sealed_json(
            a.c55_receipt.with_name("resource-policy.json"), gate["canonical_policy_sha256"]
        )

        def live_admission():
            age = (
                datetime.now(UTC) - datetime.fromisoformat(pol["snapshot"]["utc"])
            ).total_seconds()
            need(0 <= age < 3300 and window["operational_session_ready"](pol)[0], "C55 freshness")
            need(not window["concurrent"](), "concurrent build, model or transfer")

        live_admission()
        guard, pol, bound, cg = svc.admit(a, prior, HERE.parent, r, a.new_output_dir)

        class Monitor(svc.Monitor):
            def observe(self, stream):
                live_admission()
                return super().observe(stream)

        monitor = Monitor(
            guard,
            pol,
            bound,
            cg,
            a.new_output_dir / "raw/samples.jsonl",
            r["_tic"],
            elapsed_limit=WALL,
        )
        thread = threading.Thread(target=monitor.run, daemon=True)
        thread.start()
        try:
            for mode in MODES:
                recheck()
                collect_child(a, prior, monitor, r, mode, exe, env, gold, expected, pack_id)
            recheck()
        finally:
            monitor.end.set()
            thread.join(timeout=6)
            need(not thread.is_alive(), "monitor cleanup")
            monitor.check()
        need((cg / "cgroup.procs").read_text().split() == [str(os.getpid())], "unreaped children")
        modes = r["arms"]
        need(
            [v["mode"] for v in modes] == list(MODES)
            and modes[0]["proof"]["selected_bindings"] != modes[1]["proof"]["selected_bindings"]
            and modes[1]["proof"]["selected_bindings"] == modes[2]["proof"]["selected_bindings"]
            and sum(v["proof"]["pread_bytes"] for v in modes) == 1784954880
            and prior.footprint(a.new_output_dir) + 65536 < MAX_OUT,
            "policy contrast and family closure",
        )
        r.update(
            peak_bytes=int((cg / "memory.peak").read_text()),
            swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
            monitor_samples=monitor.count,
            monitor_sha256=prior.sha(a.new_output_dir / "raw/samples.jsonl"),
            cgroup_final=bound.cgroup_state(),
            cpu_stat=(cg / "cpu.stat").read_text(),
            io_stat=(cg / "io.stat").read_text(),
            c55_sha256=a.c55_sha256,
            status="PASS_REAL_CPU0_POLICY_AND_MUTANT",
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for field in (
        "build-dir",
        "input-dir",
        "manifest-dir",
        "libs",
        "c55-receipt",
        "new-output-dir",
    ):
        p.add_argument("--" + field, type=lambda x: Path(x).resolve(), required=True)
    for field in ("commit", "unit", "build-sha256", "c55-sha256"):
        p.add_argument("--" + field, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    tic = time.monotonic()
    r = {
        "status": "FAIL_PRESERVED",
        "unit": a.unit,
        "arms": [],
        "_tic": tic,
        "full_model_processes": 0,
    }

    def timeout(*_):
        raise TimeoutError("family deadline")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(WALL)
    try:
        run(a, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    del r["_tic"]
    r["elapsed_s"] = time.monotonic() - tic
    r["child_launches"] = sum(x["child_started"] for x in r["arms"])
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
