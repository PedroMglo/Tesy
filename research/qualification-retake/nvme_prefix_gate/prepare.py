"""Build the sealed slots32 canary and verify its references without opening weights."""

import argparse
import hashlib
import json
import os
import resource
import runpy
import shutil
import signal
import subprocess
import time
from pathlib import Path

from gate import DIGEST, HERE, IDS, REPO, SIZE, reference, require, sealed

PRIOR = HERE.parent / "prefix_build/attempt-01/receipt.json"
PRIOR_HASH = "b5bccd6b296d9d12ebd92cbfb9cb1404495b62f742b59d0473e29fae288f8604"
PROBE = "0b6e884649284aafcce94a184df2825185293d8daa6ff9283ac4edb04ba142c3"
C109 = REPO / "results/c109-decode-triangle-20260929T0815Z"
OBS = HERE.parent / "prefix_observer"
MIB = 1024**2
BUILD = runpy.run_path(str(HERE.parent / "prefix_build/build.py"))


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def run_prepare(raw_parent, private, backend, prev, ggml, receipt, *, slots=32):
    require(slots in (28, 32), "unknown canary profile")
    started = time.monotonic()
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "CUDA_VISIBLE_DEVICES": "",
        "TMPDIR": str(private),
    }
    stages = receipt["stages"]

    def run(cmd, name, expected=0, cwd=private):
        cmd = [str(a) for a in cmd]

        def clamp():
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 * MIB, 8 * MIB))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        of = private / (name + ".out")
        limit = False
        with (
            of.open("xb") as out,
            (private / (name + ".err")).open("xb") as err,
            subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=out,
                stderr=err,
                start_new_session=True,
                env=env,
                preexec_fn=clamp,
            ) as proc,
        ):
            peak = 0
            while proc.poll() is None:
                peak = max(peak, BUILD["rss"](proc.pid))
                if (
                    peak >= 512 * 1024
                    or time.monotonic() - started >= 90
                    or BUILD["disk"](private) >= 16 * MIB
                ):
                    os.killpg(proc.pid, signal.SIGKILL)
                    limit = True
                    break
                time.sleep(0.03)
            code = proc.wait()
        stages.append(
            {"stage": name, "exit": code, "expected_exit": expected, "tree_peak_kib_sampled": peak}
        )
        require(not limit and code == expected, "failed stage " + name)
        return of.read_bytes()

    require(
        sha(PRIOR) == PRIOR_HASH and sha(prev / "build-receipt.json") == PRIOR_HASH,
        "unknown prior build",
    )
    prior = json.loads(PRIOR.read_bytes())
    require(
        prior["status"] == "PASS_LINKED_MODEL_FREE", "private library not qualified for startup"
    )
    for p, digest in prior["imported_ggml"].items():
        require(sha(ggml / p) == digest, "GGML input changed")
    llama = prev / "cmake/bin"
    so = "libllama.so.0.0.9884"
    require(sha(llama / so) == prior["products"][so]["sha256"], "private libllama changed")

    # Compare the entire private header set with C294 Git blobs and the two observer changes.
    rows = run(
        [
            "git",
            "-C",
            backend,
            "ls-tree",
            "-r",
            prior["backend_commit"],
            "--",
            "include",
            "src",
            "ggml/include",
            "vendor/nlohmann",
        ],
        "git-blobs",
    ).decode()
    src = prev / "source"
    blob = {f: entry.split()[2] for line in rows.splitlines() for entry, f in [line.split("\t", 1)]}
    patched_dir = private / "header-check"
    (patched_dir / "src").mkdir(parents=True)
    h = "src/llama-moe-stream.h"
    (patched_dir / h).write_bytes(
        run(["git", "-C", backend, "cat-file", "blob", blob[h]], "original-layout")
    )
    observer_hashes = json.loads((OBS / "reproduced/receipt.json").read_bytes())["source_sha256"]
    require(sha(OBS / "backend.patch") == observer_hashes["backend.patch"], "changed backend patch")
    require(sha(OBS / "prefix_routes.h") == observer_hashes["prefix_routes.h"], "changed observer")
    patch = (OBS / "backend.patch").read_bytes()
    delimiter = b"--- a/src/llama-context.cpp\n"
    require(patch.count(delimiter) == 1, "unknown header patch boundary")
    header_patch = private / "service-header.patch"
    header_patch.write_bytes(patch.split(delimiter, 1)[0])
    run(
        ["git", "apply", "--no-index", header_patch],
        "derive-layout",
        cwd=patched_dir,
    )
    checked = 0
    for p in src.rglob("*"):
        if not p.is_file() or p.suffix not in {".h", ".hpp", ".inc", ".inl"}:
            continue
        rel = p.relative_to(src).as_posix()
        b = p.read_bytes()
        if rel == "src/prefix_routes.h":
            require(b == (OBS / "prefix_routes.h").read_bytes(), "observer header changed")
        elif rel == h:
            require(b == (patched_dir / h).read_bytes(), "service layout changed")
        else:
            oid = hashlib.sha1(
                b"blob " + str(len(b)).encode() + b"\0" + b, usedforsecurity=False
            ).hexdigest()
            require(blob.get(rel) == oid, "unverified header " + rel)
        checked += 1
    receipt["validated_headers"] = checked

    # The historical manifests refer to private raws. Nothing from prompts/IDs is exported.
    c110raw = raw_parent / ("c110-decode-triangle-20260929T0900Z") / "raw"
    reference(c110raw)
    observed = {}
    for name, d in [
        ("c109", C109),
        ("c110", HERE.parents[2] / "results/c110-decode-triangle-20260929T0900Z"),
    ]:
        inventory = json.loads((d / "manifest.json").read_bytes())["files"]
        raw = raw_parent / d.name / "raw"
        for arm in "abc":
            key = f"{name}-canary-{arm}.logits.f32"
            require(inventory[key] == {"bytes": SIZE, "sha256": DIGEST}, "historical arm differs")
            sealed(raw / key, SIZE, DIGEST)
            observed[key] = DIGEST
        sealed(raw / "fixture_v2.ids.tsv", 9994, IDS)
    receipt["historical_logit_sha256"] = observed

    source = REPO / "tools/c109_decode_triangle_probe.cpp"
    require(sha(source) == PROBE, "original canary source changed")
    cpp = private / "probe.cpp"
    shutil.copyfile(source, cpp)
    run(["git", "apply", "--no-index", HERE / "canary.patch"], "patch-canary")
    if slots == 28:
        gold_source = json.loads((HERE / "attempt-02/receipt.json").read_bytes())[
            "patched_source_sha256"
        ]
        require(sha(cpp) == gold_source, "unaltered canary32 source required")
        source_bytes = cpp.read_bytes()
        before, after = b"mp.moe_stream_slots=32;", b"mp.moe_stream_slots=28;"
        require(source_bytes.count(before) == 1, "ambiguous pool capacity")
        cpp.write_bytes(source_bytes.replace(before, after, 1))
        require(
            cpp.read_bytes().replace(after, before, 1) == source_bytes, "unexpected source delta"
        )
        receipt["pool_slots"] = 28

    exe = private / "nvme-prefix-canary"
    cmd = [
        "/usr/bin/c++",
        "-DGGML_BACKEND_SHARED",
        "-DGGML_SHARED",
        "-DGGML_USE_CPU",
        "-DGGML_USE_CUDA",
        "-DLLAMA_SHARED",
        "-I",
        src / "src",
        "-I",
        src / "vendor/nlohmann",
        "-I",
        src / "include",
        "-isystem",
        src / "ggml/include",
        "-ffile-prefix-map=" + str(private) + "=/tesy-canary",
        "-ffile-prefix-map=" + str(prev) + "=/tesy-prefix-build",
        "-pipe",
        "-O3",
        "-DNDEBUG",
        "-std=gnu++17",
        cpp,
        "-o",
        exe,
        "-L",
        llama,
        "-L",
        ggml,
        "-Wl,-rpath," + str(llama) + ":" + str(ggml),
        "-lllama",
        "-lggml",
        "-lggml-base",
        "-lggml-cpu",
        "-lggml-cuda",
        "-pthread",
    ]
    # Retain exactly what was executed while publishing normalized project locations.
    receipt["compile_argv"] = [
        str(x)
        .replace(str(private), "$CANARY_BUILD")
        .replace(str(prev), "$PREFIX_BUILD")
        .replace(str(ggml), "$GGML")
        for x in cmd
    ]
    run(cmd, "compile")
    linked = run(["ldd", exe], "ldd").decode()
    require("not found" not in linked, "unresolved loadable")
    files = [line.split("=>")[1].split()[0] for line in linked.splitlines() if "=>" in line]
    mapped = BUILD["map_objects"](files, prev, ggml, prior["imported_ggml"])
    require(
        all(prior["startup_mapped_objects_sha256"].get(k) == v for k, v in mapped.items()),
        "loader identity changed",
    )
    ids = c110raw / "fixture_v2.ids.tsv"
    run([exe, "--check-input", ids], "input")
    bad = private / "invalid-input"
    bad.write_text("invalid\n")
    run([exe, "--check-input", bad], "bad-input", expected=1)
    run([exe, "--check-exclusive-output", private / "no-replace"], "first-output")
    run([exe, "--check-exclusive-output", private / "no-replace"], "duplicate-output", expected=1)
    run([exe, "/absent", ids, private / "bad", "--arm", "C"], "reject-long", expected=2)
    receipt.update(
        executable_sha256=sha(exe),
        exe_bytes=exe.stat().st_size,
        patched_source_sha256=sha(cpp),
        mapped_objects_sha256=mapped,
    )
    require(
        BUILD["disk"](private) < 16 * MIB and time.monotonic() - started < 90,
        "prepare budget exceeded",
    )


def main(slots=32):
    ap = argparse.ArgumentParser(description=__doc__)
    for name in [
        "raw-parent",
        "private-workspace",
        "backend",
        "prefix-build",
        "ggml-bin",
        "new-output-dir",
    ]:
        ap.add_argument("--" + name, required=True, type=Path)
    a = ap.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    w = a.private_workspace.resolve()
    w.mkdir(mode=0o700)
    start = time.monotonic()
    result = {
        "status": "FAIL",
        "stages": [],
        "target": "NOT_RUN_PHYSICAL_ADMISSION_REQUIRED",
        "forwards": 0,
        "protocol_sha256": sha((HERE if slots == 32 else HERE / "slots28") / "protocol.md"),
        "source_sha256": {
            name: sha(HERE / name) for name in ["prepare.py", "gate.py", "canary.patch"]
        },
    }
    try:
        run_prepare(
            a.raw_parent.resolve(),
            w,
            a.backend.resolve(),
            a.prefix_build.resolve(),
            a.ggml_bin.resolve(),
            result,
            slots=slots,
        )
        result["status"] = "PASS_PREPARED_MODEL_FREE"
    except (OSError, ValueError, KeyError) as exc:
        result["error"] = str(exc)
    result["elapsed_s"] = round(time.monotonic() - start, 3)
    result["private_bytes"] = BUILD["disk"](w)
    pending = a.new_output_dir / ".pending"
    with pending.open("x") as fp:
        json.dump(result, fp, sort_keys=True, indent=2)
        fp.write("\n")
    pending.replace(a.new_output_dir / "receipt.json")
    print(result["status"], result.get("error", ""))
    raise SystemExit(int(result["status"] != "PASS_PREPARED_MODEL_FREE"))


if __name__ == "__main__":
    main()
