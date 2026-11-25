"""Build and supervise one synthetic C269 CPU_Mapped/CUDA session without a model."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SRC = run_path(HERE / "source.py")
QUAL, INT = SRC["QUAL"], SRC["INTEGRATED"]
DEVICE = INT / "t1_manager_bank/tile_transition/device"
PRE = run_path(DEVICE / "build.py")
OLD = run_path(INT / "t1_manager_cuda/device/run.py")
REVIEW = run_path(HERE / "review.py")
sha, need = PRE["sha"], PRE["need"]
PROTOCOL = "a4781b3aeeb640f6a78a229d5238325f309017ed47b01dd56e565f989aed66ad"
PRIOR = "7759c83fbac31506f2ab3455dd4ae813445ed5633e24e44ab5a769470bc4e42a"
ALIAS = "0a2d06bfd50c666427546f916806cd4cf27601deb69339674829552301092c34"


def build(a, out, paths, files):
    helpers = PRE["pre"]
    text = SRC["render"]()
    cpp = out / "device.cpp"
    cpp.write_text(text)
    links = out / "libs"
    links.mkdir()
    for name, p in paths.items():
        (links / name).symlink_to(p)
    helpers["write_vma_table"](out / "allowed.tsv", paths, files)
    inc = out / "include"
    inc.mkdir()
    legacy = REVIEW["LEGACY"]
    pin = legacy["cpu"].PIN
    for name, expected in legacy["HEADERS"].items():
        header = subprocess.check_output(
            ["git", "-C", a.backend, "show", f"{pin}:ggml/include/{name}"], timeout=10
        )
        need(hashlib.sha256(header).hexdigest() == expected, "C269 header: " + name)
        (inc / name).write_bytes(header)
    cc = Path("/usr/bin/g++-15")
    exe = out / "device"
    native = SRC["NATIVE"]
    # Headers from source.py are repository-local; the DSO selection is separately sealed.
    args = [
        cc,
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-I" + str(inc),
        "-I" + str(SRC["MIXED"]),
        "-I" + str(HERE),
        "-I" + str(native),
        cpp,
        *(
            paths[name]
            for name in (
                "libggml-cuda.so.0",
                "libggml-cpu.so.0",
                "libggml-base.so.0",
                "libcrypto.so.3",
            )
        ),
        "-Wl,-rpath-link," + str(links),
        "-ldl",
        "-o",
        exe,
    ]
    env = dict(
        PATH="/usr/bin:/bin", LC_ALL="C", LD_LIBRARY_PATH=str(links), CUDA_VISIBLE_DEVICES=""
    )
    elapsed = helpers["cpu"]["elapsed"](args, env, out / "build.log", 120)
    helpers["inspect_loader"](paths["ld-linux-x86-64.so.2"], links, exe, paths, out)
    return dict(
        binary_sha256=sha(exe),
        generated_sha256=sha(cpp),
        compiler_sha256=sha(cc),
        allowed_sha256=sha(out / "allowed.tsv"),
        loader_sha256=sha(out / "loader.json"),
        compile_s=elapsed,
        headers_sha256=legacy["HEADERS"],
        local_inputs={
            k: sha(HERE / k)
            for k in ("source.py", "alias.h", "observation.inc", "main.inc", "review.py", "run.py")
        },
    )


def parse_epochs(stdout, arm, paths):
    del paths
    fields = stdout.read_text().splitlines()
    need(arm == "alias" and len(fields) == 4, "four native endpoints")
    values = []
    for i, line in enumerate(fields):
        name, gen, pages, splits, stale, size = line.split()
        expected = (i + 1, i % 2, 7, int(i != 0), REVIEW["COUNT"])
        need(
            name == "EPOCH" and tuple(map(int, (gen, pages, splits, stale, size))) == expected,
            "generation, backing, scheduler or coverage",
        )
        values.append(
            {
                "gen": i + 1,
                "offset_bytes": (i % 2) * 13221888,
                "splits": int(splits),
                "stale_rejected": bool(i),
            }
        )
    return values


def execute(a, out, r):
    r["commit"] = a.commit
    r["tree"] = PRE["pre"]["freeze"](a.commit)
    need(
        sha(HERE / "protocol.md") == PROTOCOL
        and sha(HERE.parent / "evidence/receipt.json") == ALIAS
        and sha(SRC["MIXED"] / "receipts/v3-r01-native.json")
        == "26b2136d2bdb023f6126d7c4f8a80ac0e47e2d8a20a05a220615e12aad6f7825"
        and sha(SRC["MIXED"].parent / "packed_cpu_views/operator.cpp")
        == REVIEW["LEGACY"]["FROZEN"]["operator.cpp"],
        "frozen geometry and independent references",
    )
    cold = run_path(INT / "cold_read_fixture/runner.py")
    io, load = cold["io"], cold["load"]
    io.CAP, io.STOPS = 2**31, 1856 << 20
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "dedicated child scope")
    paths, files = PRE["providers"](a.map)
    PRE["verify_files"](paths, files)
    acquisition = run_path(QUAL / "packed_layer_service/profile.py")
    provider, unchanged = acquisition["monitor_provider"](SimpleNamespace(token=io.stat_id))
    prior = load(a.prior, PRIOR)
    need(
        prior["status"] == "PASS_C291_TILE_TRANSITION_CUDA_FAMILY"
        and prior["provider"] == provider,
        "CUDA/NVML closure",
    )
    c55 = load(a.c55, a.c55_sha256)
    policy = load(a.c55.with_name("resource-policy.json"), c55["canonical_policy_sha256"])
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "C55 admission",
    )
    r.update(
        protocol_sha256=PROTOCOL,
        model_forwards=0,
        provider=provider,
        acquisition_sha256=sha(SRC["NATIVE"] / "run.py"),
        c269=REVIEW["LEGACY"]["cpu"].PIN,
        map_sha256=sha(a.map),
        c55_sha256=a.c55_sha256,
        alias_sha256=ALIAS,
    )
    r["build"] = build(a, out, paths, files)
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(0 <= age < 3300 - 95, "fresh C55")
    (out / "raw").mkdir()
    (out / "alias").mkdir()
    # Each run_path produces a private module namespace. Only the terminal stdout schema
    # changes; the entire inventory, VMAs, PID handoffs and cleanup execute unmodified.
    case = OLD["case"]
    case.__globals__["parse"] = parse_epochs
    active = run_path(INT / "t1_native_sink/measure.py")["active_sample"]
    r["process"] = case(out, "alias", a.unit, out, io, policy, cold, active, paths)
    r["numbers"] = REVIEW["review"](out / "alias")
    obs = io.monitor(policy)["observation"]
    need(not obs["gpu_owners"], "GPU not released")
    r["gpu_after_mib"] = obs["gpu"]["used_mib"]
    r["cgroup_peak_bytes"] = io.scope()
    need(sha(out / "device") == r["build"]["binary_sha256"], "binary changed")
    PRE["verify_files"](paths, files)
    unchanged()
    r["raw_bytes"] = sum(
        p.stat().st_size for p in out.rglob("*") if p.is_file() and not p.is_symlink()
    )
    need(r["raw_bytes"] < 32 << 20, "output budget")
    r["status"] = "PASS_CPU_MAPPED_MIXED_GENERATIONS"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for nm in ("commit", "unit", "c55-sha256"):
        p.add_argument("--" + nm, required=True)
    for nm in ("backend", "map", "c55", "prior", "new-output-dir"):
        p.add_argument("--" + nm, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = {"status": "FAIL_PRESERVED"}
    tic = time.monotonic()

    def stop(*_):
        raise TimeoutError("family deadline")

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(240)
    try:
        execute(a, out, r)
    except Exception as e:
        r["reason"] = f"{type(e).__name__}: {e}"
    finally:
        signal.alarm(0)
    r["family_wall_s"] = time.monotonic() - tic
    (out / "receipt.json").write_text(
        json.dumps(r, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
