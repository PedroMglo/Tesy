"""Relink PFJ1, verify C270/C281 loader selections and exercise the shipped manager object."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SNAP = HERE.parent
PFJ = SNAP.parents[1]
QUAL = PFJ.parents[1]
old = run_path(PFJ / "build.py")
snap = run_path(SNAP / "run.py")
rv = run_path(SNAP / "review.py")
need, sha, git, cmd = (old[k] for k in ("need", "sha", "git", "cmd"))
PROTOCOL = "faeda8fc46a3085b156bf60f2faa45d227a508f224c1edfffba1a98d797bef04"
FIXTURE = "73b691d2ffcfb046dd2fe446387c2967c898c6ea1c10c7ce220b7320770e616b"
PFJ_CONTROL = "911b3be5b529d8e07409c12cf600ca9f7f6182f7a397fc6de265e5ea4be254eb"


def pinned_json(path, expected):
    need(sha(path) == expected, "hash " + path.name)
    return json.loads(path.read_bytes())


def cpu_cases(backend, out, prior, seeds, r, env, deadline):
    build = backend / "build-c269-cuda"
    support = [
        build / s
        for s in (
            "src/CMakeFiles/llama.dir/llama-mmap.cpp.o",
            "src/CMakeFiles/llama.dir/llama-impl.cpp.o",
            "bin/libggml-base.so.0.15.3",
        )
    ]
    common = [old["CXX"], "-std=c++17", "-O1", "-fPIC", "-g0", "-pthread"]
    common.extend("-I" + str(backend / d) for d in ("src", "include", "ggml/include"))
    cpu_env = env | {
        "LD_LIBRARY_PATH": str(support[-1].parent),
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "1",
    }

    def execute(argv, stdout, stderr, extra=None):
        with stdout.open("xb") as f, stderr.open("xb") as e:
            subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=f,
                stderr=e,
                env=cpu_env | (extra or {}),
                check=True,
                timeout=max(0.01, deadline - time.monotonic()),
            )

    candidate = out / "cpu-candidate"
    previous = out / "cpu-pfj1"
    for destination, headers, objects, modes in (
        (candidate, out / "overlay", out / "candidate", snap["ARMS"]),
        (previous, prior / "overlay/src", prior / "candidate", ("off", "heat-a")),
    ):
        destination.mkdir()
        exe = destination / "fixture"
        mgr = objects / "llama-moe-stream.cpp.o"
        execute(
            [*common, "-I" + str(headers), SNAP / "fixture.cpp", mgr, *support, "-o", exe],
            destination / "build.stdout",
            destination / "build.stderr",
        )
        execute(["/usr/bin/ldd", exe], destination / "loader", destination / "loader.stderr")
        text = (destination / "loader").read_text()
        names = [x.split()[0] for x in text.splitlines() if x.strip()]
        need(
            "not found" not in text
            and "libggml-base.so.0" in names
            and not any(k in name for k in ("cuda", "cublas", "nvidia", "llama") for name in names),
            "fixture CPU loader",
        )
        r.setdefault("cpu_objects", {})[destination.name] = dict(
            executable_sha256=sha(exe), manager_sha256=sha(mgr)
        )
        for mode in modes:
            d = destination / mode
            d.mkdir()
            extra = {"TESY_PHASE_FD_FILE": str(d / "journal.pfj")}
            if mode != "off":
                extra["TESY_PFJ_POLICY_SNAPSHOT"] = str(d / "policy.bin")
            execute([exe, mode, d / "empty.bin"], d / "native.json", d / "stderr", extra)
    report = rv["family"](candidate)
    read = run_path(rv["PFJ_SOURCE"])["read_journal"]
    for arm in ("off", "heat-a"):
        d = previous / arm
        need(not (d / "policy.bin").exists(), "prior PFJ1 unexpectedly enables policy")
        rows, _ = read(d / "journal.pfj")
        _, projection, _, _ = rv["witness"](rows, arm)
        need(
            projection == report["arms"][arm]["projection_sha256"]
            and json.loads((d / "native.json").read_bytes()) == report["arms"][arm]["choices"],
            "historical PFJ1 control",
        )
    for arm in snap["ARMS"]:
        for key in ("projection_sha256", "sidecar_sha256", "choices", "status", "matches"):
            need(
                report["arms"][arm][key] == seeds["verified"]["arms"][arm][key],
                "seed parity " + key,
            )
    r["fixture"] = report


def build(a, out, r, start):
    native = a.backend.resolve(strict=True)
    prior, pre = a.pfj_build.resolve(strict=True), a.preflight_dir.resolve(strict=True)
    b = native / "build-c269-cuda"
    need(
        sha(HERE / "build-protocol.md") == PROTOCOL
        and git(HERE, "rev-parse", "HEAD") == a.commit
        and not git(HERE, "status", "--porcelain")
        and not git(native, "status", "--porcelain")
        and git(native, "rev-parse", "HEAD") == old["WORKER"],
        "clean code and protocol",
    )
    cgroup = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().removeprefix(
        "0::/"
    )
    need(
        cgroup.name == a.unit + ".scope"
        and (cgroup / "memory.max").read_text().strip() == str(2**31)
        and (cgroup / "memory.swap.max").read_text().strip() == "0",
        "expected isolated build scope",
    )
    initial = (cgroup / "memory.events").read_text()
    seeds = pinned_json(SNAP / "receipt.json", FIXTURE)
    prev = pinned_json(prior / "receipt.json", snap["PRIOR"])
    manifest = json.loads((prior / "inputs.json").read_bytes())
    need(
        len(manifest) == 171
        and old["stamp"](manifest) == old["INPUTS"] == prev["inputs_sha256"]
        and all(sha(b / f) == h for f, h in manifest.items()),
        "171 authenticated link inputs",
    )
    need(
        prev["status"] == "PASS_C269_PHASE_FD_PRIVATE_BUILD"
        and prev["candidate_sha256"] == PFJ_CONTROL == sha(prior / prev["candidate_file"])
        and prev["gold_sha256"] == old["ORIGINAL"] == sha(prior / prev["gold_file"])
        and sha(b / "compile_commands.json") == old["DB"]
        and sha(b / "build.ninja") == old["NINJA"]
        and sha(b / "CMakeFiles/rules.ninja") == old["RULES"]
        and sha(old["CXX"]) == prev["compiler_sha256"]
        and sha(cmd(old["CXX"], "-print-prog-name=cc1plus")) == prev["cc1plus_sha256"]
        and sha("/usr/bin/ld") == prev["linker_sha256"],
        "build provenance",
    )
    authority = pinned_json(pre / "receipt.json", old["PREFLIGHT"])
    arms = pinned_json(pre / "static-map.json", authority["static_map_sha256"])["arms"]
    stock = old["module"](QUAL / "stock_prefault_build/build.py", "policy_build_stock")
    static = old["module"](
        QUAL / "nvme_r0_gate/driver_pair/server_startup/screen.py", "policy_build_static"
    )
    need(
        sha(static.__file__) == authority["source_sha256"]
        and all(sha(v["executable"]) == v["executable_sha256"] for v in arms.values()),
        "startup evidence",
    )
    header = snap["overlay"](out / "overlay", prior, prev["overlay_sha256"])
    need(
        sha(header) == seeds["header_sha256"]
        and all(
            sha(out / "overlay" / Path(f).name) == h
            for f, h in prev["overlay_sha256"].items()
            if f.endswith(".cpp")
        ),
        "exact qualified policy source",
    )
    phase = out / "candidate"
    phase.mkdir()
    gold = out / prev["gold_file"]
    gold.parent.mkdir()
    shutil.copyfile(prior / prev["gold_file"], gold)
    (gold.parent / old["SONAME"]).symlink_to(old["IMAGE"])
    r.update(
        stage="compile",
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        worker_commit=old["WORKER"],
        original_sha256=old["ORIGINAL"],
        gold_sha256=sha(gold),
        gold_file=prev["gold_file"],
        fixture_receipt_sha256=seeds["source_receipt_sha256"],
        prior_build_sha256=snap["PRIOR"],
        pfj_control_sha256=PFJ_CONTROL,
        policy_header_sha256=sha(SNAP / "snapshot.h"),
        overlay_header_sha256=sha(header),
        protocol_sha256=PROTOCOL,
        static_preflight_sha256=old["PREFLIGHT"],
        inputs_sha256=old["INPUTS"],
        program_sha256=sha(Path(__file__)),
        compiler_sha256=prev["compiler_sha256"],
        objects={},
    )
    database = json.loads((b / "compile_commands.json").read_bytes())
    env = old["ENV"] | {"TMPDIR": str(phase)}
    deadline = start + 115
    for src in old["SOURCES"]:
        (row,) = [x for x in database if Path(x["file"]).resolve() == native / src]
        cc = shlex.split(row["command"])
        need(
            Path(row["directory"]).resolve() == b
            and cc[0] == old["CXX"]
            and cc[-4:] == ["-o", old["obj"](src), "-c", row["file"]],
            "compile recipe",
        )
        cc[1:1] = [f"-fmacro-prefix-map={header.parent}={Path(row['file']).parent}"]
        obj = phase / Path(old["obj"](src)).name
        cc[-3], cc[-1] = str(obj), str(header.parent / Path(src).name)
        stock.produce(cc, b, phase / (obj.name + ".log"), env, deadline)
        r["objects"][src] = sha(obj)
    r["stage"] = "link"
    tokens = shlex.split(
        cmd("ninja", "-C", b, "-t", "commands", "bin/" + old["IMAGE"]).splitlines()[-1]
    )
    need(old["stamp"](tokens) == old["LINK"], "link recipe")
    stock.produce(old["link_args"](tokens, phase), b, phase / "link.log", env, deadline)
    image = phase / old["IMAGE"]
    digest = sha(image)
    (phase / old["SONAME"]).symlink_to(old["IMAGE"])
    abi = stock.abi(image)
    ctrl = prior / prev["candidate_file"]
    opt_in = b"TESY_PFJ_POLICY_SNAPSHOT\x00"
    need(
        digest != PFJ_CONTROL
        and opt_in in image.read_bytes()
        and opt_in not in ctrl.read_bytes()
        and old["symbols"](ctrl) == old["symbols"](image)
        and abi == prev["phases"]["candidate"]["abi"],
        "ELF dynamic or exports ABI",
    )
    r.update(
        candidate_file=str(image.relative_to(out)),
        candidate_sha256=digest,
        abi=abi,
        stage="static_startup",
        startup={},
    )
    files = static.Files()
    for k, arm in arms.items():
        maps = r["startup"][k] = {}
        for mode, path, h in (
            ("gold", gold, old["ORIGINAL"]),
            ("pfj_control", ctrl, PFJ_CONTROL),
            ("candidate", image, digest),
        ):
            maps[mode] = old["verify"](
                arm, mode, path, authority["arms"][k]["objects"], h, static, files
            )
        need(
            maps["gold"] == prev["startup"][k]["gold"]
            and maps["pfj_control"] == prev["startup"][k]["candidate"],
            "historical selections",
        )
    r["stage"] = "control_and_candidate_cpu_objects"
    need(
        sha(prior / "candidate/llama-moe-stream.cpp.o")
        == prev["phases"]["candidate"]["objects"][old["MGR"]],
        "control object",
    )
    cpu_cases(native, out, prior, seeds, r, env, deadline)
    need(
        all(sha(b / f) == h for f, h in manifest.items())
        and sha(ctrl) == PFJ_CONTROL
        and sha(image) == digest,
        "unchanged inputs, control and candidate",
    )
    used = sum(p.stat().st_size for p in out.rglob("*") if p.is_file() and not p.is_symlink())
    need(
        used + 131072 <= 128 * 2**20
        and initial == (cgroup / "memory.events").read_text()
        and int((cgroup / "memory.swap.current").read_text()) == 0,
        "build budget",
    )
    r.update(
        status="PASS_C269_PHASE_FD_PRIVATE_BUILD",
        policy_status="PASS_POLICY_DSO_CPU_BUILD_ONLY",
        stage="closed",
        scope_peak=int((cgroup / "memory.peak").read_text()),
        output_bytes_before_receipt=used,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("commit", "unit"):
        p.add_argument("--" + k, required=True)
    for k in ("backend", "pfj-build", "preflight-dir", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED", stage="admission", server_starts=0, gpu_calls=0, model_forwards=0
    )
    try:
        build(a, out, r, start)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        r["reason"] = str(exc)
    r["elapsed_s"] = time.monotonic() - start
    tmp = out / "receipt.tmp"
    tmp.write_text(json.dumps(r, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(out / "receipt.json")
    print(r["status"], r["stage"], r.get("reason", ""))
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))
