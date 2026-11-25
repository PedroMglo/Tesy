"""Synthetic C291 CPU worker gate. All children inherit one externally bounded scope."""

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import resource
import signal
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "c89c88b342054223e3f27a17fbfd0954803147ac"
TREE = "3962daa588dfa89971c60c95ce4c5054bc27fd3f"
LIBS = {
    "ggml": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
    "crypto": "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72",
}
SCOPE_SHA = "385556de0929051fb526c8f98012c461b318172844d9ec5c8f16fedc4d2b7ff4"
CORE = tuple(
    "src/" + name
    for name in (
        "llama-moe-stream.cpp",
        "llama-moe-stream.h",
        "llama-mmap.cpp",
        "llama-mmap.h",
        "llama-impl.cpp",
        "llama-impl.h",
        "c269-last-use-order.h",
        "c291-direct-reader.h",
        "c291-expert-store.h",
    )
)
BUILD_INPUTS = ("llama-moe-stream.cpp", "llama-impl.cpp", "llama-mmap.cpp")
SLAB, WINDOW, STRIDE = 4_406_400, 13_221_888, 13_258_752
MAX_RAM, MAX_NVME, WALL, CHILD = 1 << 30, 192 << 20, 720, 180
CASES = (
    ("DENSE", "success"),
    ("STAGED", "success"),
    ("DIRECT", "success"),
    ("DENSE", "short"),
    ("STAGED", "short"),
    ("DIRECT", "short"),
    ("STAGED", "short_tail"),
    ("DIRECT", "short_tail"),
    ("DENSE", "shutdown"),
    ("STAGED", "shutdown"),
    ("DIRECT", "shutdown"),
)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def canonical(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def utc():
    return datetime.now(UTC).isoformat()


def cmd(argv, cwd=None):
    return subprocess.check_output(argv, cwd=cwd, timeout=15)


def git(root, *args):
    return cmd(
        [
            "git",
            "--no-replace-objects",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            root,
            *args,
        ]
    )


def extract(backend, destination):
    # Source-list precedent: C305 manager/run.py. No runtime dependency on that branch.
    need(git(backend, "rev-parse", PIN + "^{tree}").decode().strip() == TREE, "C291 tree")
    entries = git(
        backend, "ls-tree", "-r", "-z", PIN, "ggml/include", "include", "vendor/nlohmann", *CORE
    ).split(b"\0")[:-1]
    need(len(entries) == 34, "expected 25 public/vendored headers plus nine native files")
    destination.mkdir()
    files = {}
    for entry in entries:
        mode_oid, name = entry.decode().split("\t")
        mode, kind, oid = mode_oid.split()
        need((mode, kind) == ("100644", "blob"), "not an ordinary pinned file")
        blob = git(backend, "cat-file", "blob", oid)
        need(
            hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest() == oid,
            "Git blob content does not match the authenticated tree",
        )
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(blob)
        files[name] = {"oid": oid, "bytes": len(blob), "sha256": sha(path)}
    need(set(CORE) <= files.keys(), "missing C291 private source")
    return files


def apply_runtime(patch, private, run):
    # GNU patch operates only on the extracted directory. A git apply from a
    # surrounding worktree could instead resolve paths at its worktree root.
    names = cmd(["git", "apply", "--numstat", "-z", patch], cwd="/").decode().split("\0")[:-1]
    changed = [row.split("\t", 2)[2] for row in names]
    need(
        changed
        and len(set(changed)) == len(changed)
        and all(re.fullmatch(r"src/[A-Za-z0-9_.-]+\.(cpp|h)", n) for n in changed),
        "patch must only change private backend sources",
    )
    before = {p.relative_to(private).as_posix(): sha(p) for p in private.rglob("*") if p.is_file()}
    run(
        ["patch", "--batch", "--forward", "--fuzz=0", "-d", private, "-p1", "-i", patch],
        "apply-runtime",
    )
    paths = [p for p in private.rglob("*") if p.is_file() or p.is_symlink()]
    need(all(p.is_file() and not p.is_symlink() for p in paths), "unexpected patched file type")
    after = {p.relative_to(private).as_posix(): sha(p) for p in paths}
    need(
        {n for n in before.keys() | after.keys() if before.get(n) != after.get(n)} == set(changed),
        "actual patch delta disagrees with declared paths",
    )
    return {name: after.get(name) for name in sorted(changed)}


def cgroup_reader(project, unit):
    path = project / "research/qualification-retake/stock_prefault_resident/runner.py"
    need(sha(path) == SCOPE_SHA, "cgroup reader source has changed")
    spec = importlib.util.spec_from_file_location("tesy_private_scope_reader", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cg = mod.actual_scope(unit)

    def observe():
        s = mod.snapshot(cg)
        need(
            s["memory.max"] == MAX_RAM
            and s["memory.swap.max"] == 0
            and s["memory.swap.current"] == 0
            and 0 < s["memory.peak"] <= MAX_RAM
            and s["sole_process"]
            and not any(s["memory.events"][k] for k in ("oom", "oom_kill", "oom_group_kill")),
            "required sole dedicated 1 GiB / swap-zero scope or memory events",
        )
        return s

    return observe


def record_command(argv, out, label, env, report, deadline, observe):
    directory = out / label
    directory.mkdir()
    before = observe()
    row = {"started_utc": utc(), "argv": list(map(str, argv)), "scope_before": before}
    report[label] = row
    start = time.monotonic()

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_NVME, MAX_NVME))

    try:
        with (directory / "stdout").open("xb") as so, (directory / "stderr").open("xb") as se:
            remaining = min(CHILD, deadline - start)
            need(remaining > 0, "campaign exhausted its 720 s wall budget")
            command = ["/usr/bin/time", "-f", "%M", "-o", directory / "maxrss.kib", *argv]
            with subprocess.Popen(
                command,
                stdout=so,
                stderr=se,
                cwd=directory,
                env=env,
                start_new_session=True,
                preexec_fn=limits,
            ) as child:
                try:
                    rc = child.wait(timeout=remaining)
                except BaseException:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    raise
            row["returncode"] = rc
        row["maxrss_kib"] = int((directory / "maxrss.kib").read_text().splitlines()[-1])
        need(
            rc == 0 and row["maxrss_kib"] < MAX_RAM // 1024, "nonzero child or RSS limit: " + label
        )
    finally:
        row.update(finished_utc=utc(), wall_s=round(time.monotonic() - start, 6))
        row["logs"] = {
            name: {"sha256": sha(p), "bytes": p.stat().st_size}
            for name in ("stdout", "stderr", "maxrss.kib", "raw.json")
            if (p := directory / name).is_file()
        }
        row["scope_after"] = observe()
    return directory


def compile_fixture(private, label, backend_lib, crypto, out, run):
    exe = out / ("worker-" + label)
    cxx = "/usr/bin/g++"
    args = [
        cxx,
        "-std=c++17",
        "-DTESY_STORE_TESTING",
        "-pthread",
        "-O0",
        "-g0",
        "-Wall",
        "-Wextra",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-ffunction-sections",
        "-fdata-sections",
    ]
    args += ["-I" + str(private / d) for d in ("src", "include", "ggml/include")]
    args += [
        HERE / "fixture.cpp",
        *(private / "src" / s for s in BUILD_INPUTS),
        "-Wl,--gc-sections",
        "-Wl,--wrap=pread",
        "-Wl,--wrap=ggml_backend_tensor_set",
        backend_lib,
        crypto,
        "-ldl",
        "-o",
        exe,
    ]
    run(args, "build-" + label)
    log = run(["/usr/bin/ldd", exe], "loader-" + label)
    output = (log / "stdout").read_text()
    need(
        not any(x in output.lower() for x in ("not found", "libllama", "cuda", "nvidia")),
        "unexpected loader",
    )
    load = {}
    for name, soname in (("ggml", "libggml-base.so.0"), ("crypto", "libcrypto.so.3")):
        paths = re.findall(r"^\s*" + re.escape(soname) + r"\s*=>\s*(/\S+)", output, re.M)
        need(len(paths) == 1 and sha(Path(paths[0])) == LIBS[name], "wrong linked " + name)
        load[name] = str(Path(paths[0]).resolve())
    return exe, {"sha256": sha(exe), "load_paths": load}


def identity(path):
    st = path.stat()
    return {
        "dev": st.st_dev,
        "inode": st.st_ino,
        "size_bytes": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "ctime_ns": st.st_ctime_ns,
    }


def verify(raw, mode, case, gold, pack_id, membership):
    need(
        raw["status"] == "PASS_SYNTHETIC_WORKER_FIXTURE"
        and raw["mode"] == mode
        and raw["case"] == case
        and raw["model_forwards"] == 0
        and raw["manager_destructor_returned"] is True,
        "arm identity",
    )
    need(raw["cgroup_membership"] == membership, "child escaped the dedicated scope")
    pack = raw["pack"]
    need(
        pack["sha256_from_serviced_fd"]
        == pack["declared_write_stream_sha256"]
        == gold["pack_sha256"]
        and pack["bytes"] == pack["proof_scan_DIO_bytes"] == 6 * STRIDE
        and pack["identity"] == pack_id,
        "child source identity or scan accounting",
    )
    for name, required in LIBS.items():
        need(
            sha(Path(raw["mapped_providers"][name])) == required,
            "unexpected actual provider: " + name,
        )
    native = raw["native"]
    need(
        native["workers"] == 4
        and set(native)
        == {"workers", "calls", "hits", "misses", "store_loads", "store_read_logical"},
        "native accounting schema",
    )
    align = pack["alignment_offset"]
    n = (3 * SLAB + align - 1) // align * align if mode == "DENSE" else WINDOW
    ordered = sorted(raw["observed_claims"], key=lambda j: (j["phase"], j["expert"]))
    if case == "success":
        expected = [("four", v, v, 1) for v in range(36, 40)] + [("replace", 40, 0, 2)]
        need(
            native
            == dict(
                workers=4,
                calls=12,
                hits=7,
                misses=41,
                store_loads=41,
                store_read_logical=41 * 3 * SLAB,
            ),
            "native remap accounting",
        )
        for phase, change in (("before_replacement", False), ("after_replacement", True)):
            rows = []
            for slot in range(40):
                expert = 40 if change and slot == 0 else slot
                rec = 0 if expert < 36 else expert - 35
                rows.append(
                    dict(
                        slot=slot,
                        expert=expert,
                        generation=2 if expert != slot else 1,
                        role_sha256=gold["records"][rec]["role_sha256"],
                    )
                )
            need(raw[phase] == rows, "independent published slabs or generations")
        need(len({j["worker_tid"] for j in ordered[:4]}) == 4, "four distinct overlapping workers")
        counts = {"warm": 36, "four": 4, "hits": 0, "replace": 1}
        invariant = {k: raw[k] for k in ("before_replacement", "after_replacement", "native")}
    else:
        expected = [("fault", 36, 0, 1)]
        need(
            native
            == dict(workers=4, calls=0, hits=0, misses=0, store_loads=0, store_read_logical=0),
            "failed/cancelled service incorrectly published",
        )
        need(
            raw["terminal_state"]
            == dict(
                slot=0,
                generation=1,
                claimed=False,
                state="LOADING",
                native_loads_committed=0,
                sticky_load_failed=(case != "shutdown"),
                shutting_down=(case == "shutdown"),
            ),
            "error or shutdown terminal",
        )
        counts = {"fault": 1}
        invariant = {"native": native, "terminal": raw["terminal_state"]}
    need(
        [(j["phase"], j["expert"], j["slot"], j["gen"]) for j in ordered] == expected,
        "worker claim assignment",
    )
    for j in ordered:
        short = case == "short"
        actual = n - (4096 if short else 0)
        returned = 3 * SLAB if case == "short_tail" else actual
        need(
            j["worker_tid"] > 0
            and j["requested"] == n
            and j["syscall_return"] == actual
            and j["reader_return"] == returned
            and j["publish_expected"] == (case == "success"),
            "read witness",
        )
        direct = mode == "DIRECT"
        need(
            j["pread_dst_class"] == ("OWNED_SLOT_BASE" if direct else "OUTSIDE_CACHE")
            and j["direct_dst_offset_from_slot0"] == (j["slot"] * WINDOW if direct else None),
            "pread destination ownership",
        )
        expected_sets = 0 if direct or case in ("short", "short_tail") else 3
        if case == "shutdown":
            need(len(j["sets"]) <= expected_sets, "cancelled SET count")
        else:
            need(len(j["sets"]) == expected_sets, "SET count")
        step = SLAB if mode == "DENSE" else WINDOW
        need(
            j["sets"]
            == [
                dict(
                    component=k,
                    src_delta_from_pread_dst=k * SLAB,
                    dst_delta_from_role_view=j["slot"] * step,
                )
                for k in range(len(j["sets"]))
            ],
            "SET source/destination",
        )
    need(set(counts) == raw["phases"].keys(), "phase conservation")
    for ph, quantity in counts.items():
        sets = (
            (0 if mode == "DIRECT" else 3) * quantity
            if case == "success"
            else len(ordered[0]["sets"])
        )
        delivered = quantity * (
            3 * SLAB if case == "short_tail" else n - (4096 if case == "short" else 0)
        )
        need(
            raw["phases"][ph]
            == dict(
                reads=quantity,
                sets=sets,
                requested=quantity * n,
                delivered=delivered,
                bytes_set=sets * SLAB,
            ),
            "service bytes per phase: " + ph,
        )
    return canonical(invariant)


def publish(out, row):
    temporary = out / "receipt.pending"
    final = out / "receipt.json"
    with temporary.open("x") as f:
        json.dump(row, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.link(temporary, final)
    temporary.unlink()


def validate_origin(args, r, gold):
    need(
        args.original_receipt is not None
        and args.original_sha256
        and sha(args.original_receipt) == args.original_sha256,
        "authenticated prior DENSE receipt required",
    )
    base = json.loads(args.original_receipt.read_bytes())
    need(
        base["status"] == "PASS_ORIGINAL_DENSE"
        and base["phase"] == "original"
        and base["c291"] == r["c291"]
        and base["providers"] == LIBS
        and base["pack"]["sha256"] == gold["pack_sha256"]
        and all(
            base["source_files"][p] == r["source_files"][p]
            for p in ("generate.py", "fixture.cpp", "run.py")
        ),
        "prior reference is not the same experiment",
    )
    ref = base["arms"]["original-DENSE-success"]
    path = args.original_receipt.parent / "original-DENSE-success" / "raw.json"
    need(sha(path) == ref["raw_sha256"], "original raw reference was altered")
    check = verify(
        json.loads(path.read_bytes()),
        "DENSE",
        "success",
        gold,
        base["pack"]["identity"],
        base["scope_membership"],
    )
    need(check == ref["invariant_sha256"], "inconsistent prior reference")
    return check


def run_campaign(args):
    out = args.new_output.resolve()
    nvme = args.new_nvme_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(
        schema="c291-synthetic-worker-packed-v1",
        status="FAIL_PRESERVED",
        started_utc=utc(),
        phase=args.phase,
        commands={},
        arms={},
        builds={},
        providers=LIBS,
        budget=dict(
            total_wall_s=WALL,
            per_child_wall_s=CHILD,
            memory_max=MAX_RAM,
            memory_swap_max=0,
            synthetic_storage_max=MAX_NVME,
        ),
    )
    start = time.monotonic()
    deadline = start + WALL

    def interrupt(signum, _frame):
        raise RuntimeError("terminal signal " + signal.Signals(signum).name)

    signal.signal(signal.SIGALRM, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    signal.alarm(WALL)
    try:
        if args.phase == "candidate":
            need(
                args.original_receipt and sha(args.original_receipt) == args.original_sha256,
                "authenticated original required before incurring candidate work",
            )
            prior = json.loads(args.original_receipt.read_bytes())
            previous_seconds = prior["total_wall_s"]
            need(
                prior["status"] == "PASS_ORIGINAL_DENSE" and 0 < previous_seconds < WALL - 1,
                "missing or expired original reference",
            )
            r["prior_wall_s"] = previous_seconds
            deadline -= previous_seconds
            signal.alarm(int(deadline - time.monotonic()))
        project = args.project_root.resolve() if args.project_root else HERE.parents[2]
        probe = project / "research/qualification-retake"
        need(
            HERE.is_relative_to(probe) and HERE != probe,
            "runner must be installed in the sealed project checkout",
        )
        need(
            not git(project, "status", "--porcelain", "--untracked-files=normal").strip(),
            "dirty Tesy checkout",
        )
        r["commit"], r["tree"] = (
            git(project, "rev-parse", "HEAD", "HEAD^{tree}").decode().splitlines()
        )
        files = ["run.py", "fixture.cpp", "generate.py"]
        for opt in ("protocol.md", "protocolo.md"):
            if (HERE / opt).is_file():
                files.append(opt)
        need(len(files) > 3, "missing frozen prospective protocol")
        r["source_files"] = {}
        for name in files:
            file = HERE / name
            blob = git(project, "show", "HEAD:" + file.relative_to(project).as_posix())
            need(sha(file) == hashlib.sha256(blob).hexdigest(), "unsealed runner input " + name)
            r["source_files"][name] = sha(file)
        patch = args.patch.resolve() if args.patch else HERE / "arena.patch"
        if args.phase != "original":
            blob = git(project, "show", "HEAD:" + patch.relative_to(project).as_posix())
            need(sha(patch) == hashlib.sha256(blob).hexdigest(), "unsealed runtime patch")
            r["patch_sha256"] = sha(patch)
        observe = cgroup_reader(project, args.scope_unit)
        r["scope_before"] = observe()
        r["scope_membership"] = Path("/proc/self/cgroup").read_text().strip()
        need(
            not nvme.exists()
            and not nvme.is_relative_to(out)
            and not out.is_relative_to(nvme)
            and nvme.parent.is_dir(),
            "fresh separate NVMe fixture destination",
        )
        mount = json.loads(
            cmd(["findmnt", "--json", "--target", nvme.parent, "--output", "FSTYPE,SOURCE"])
        )["filesystems"]
        need(
            len(mount) == 1
            and mount[0]["fstype"] == "btrfs"
            and re.fullmatch(r"/dev/nvme\d+n\d+(?:p\d+)?(?:\[.*\])?", mount[0]["source"]),
            "destination must resolve to the project's internal NVMe Btrfs",
        )
        r["nvme_mount"] = mount[0]
        backend = args.backend.resolve()
        default_lib = (
            backend.parent / "c269-layer-last-use/build-c269-cuda/bin/libggml-base.so.0.15.3"
        )
        base_dso = (args.base_dso or default_lib).resolve(strict=True)
        crypto = args.crypto.resolve(strict=True)
        need(
            sha(base_dso) == LIBS["ggml"] and sha(crypto) == LIBS["crypto"],
            "pinned C269 base and OpenSSL",
        )
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(out),
            "TMPDIR": str(out),
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "CUDA_VISIBLE_DEVICES": "",
            "MALLOC_ARENA_MAX": "2",
            "OMP_NUM_THREADS": "1",
            "LD_LIBRARY_PATH": str(base_dso.parent),
        }

        def run(argv, label):
            return record_command(argv, out, label, env, r["commands"], deadline, observe)

        ver = run(["/usr/bin/g++", "--version"], "compiler")
        r["toolchain"] = {
            "compiler_sha256": sha(Path("/usr/bin/g++")),
            "version": (ver / "stdout").read_text().splitlines()[0],
            "openssl_digest": LIBS["crypto"],
            "scope_reader_sha256": SCOPE_SHA,
        }
        run(
            [sys.executable, "-I", "-B", HERE / "generate.py", "--new-output-dir", nvme],
            "generate",
        )
        need(
            {p.name for p in nvme.iterdir()} == {"gold.json", "experts.pack"},
            "unexpected generated files",
        )
        goldfile = nvme / "gold.json"
        pack = nvme / "experts.pack"
        pack_id = identity(pack)
        gold = json.loads(goldfile.read_bytes())
        need(
            pack_id["size_bytes"] == 6 * STRIDE
            and pack_id["size_bytes"] + goldfile.stat().st_size < MAX_NVME
            and pack.stat().st_blocks * 512 + goldfile.stat().st_blocks * 512 < MAX_NVME
            and all(
                stat.S_ISREG(f.lstat().st_mode) and not f.stat().st_mode & 0o222
                for f in (goldfile, pack)
            ),
            "synthetic storage/readonly guard",
        )
        gold_hash = sha(goldfile)
        r["pack"] = dict(
            identity=pack_id,
            sha256=gold["pack_sha256"],
            gold_sha256=gold_hash,
            allocated_bytes=pack.stat().st_blocks * 512,
        )
        (out / "gold.json").write_bytes(goldfile.read_bytes())
        r["c291"] = {"commit": PIN, "tree": TREE, "blobs": extract(backend, out / "original-src")}
        expected = {}
        if args.phase == "candidate":
            expected["success"] = validate_origin(args, r, gold)
            r["prior_original_receipt_sha256"] = args.original_sha256

        def arm(exe, build, mode, case):
            label = f"{build}-{mode}-{case}"
            rawpath = out / label / "raw.json"
            need(identity(pack) == pack_id and sha(goldfile) == gold_hash, "mutated arm inputs")
            run([exe, mode, case, pack, goldfile, rawpath], label)
            need(
                identity(pack) == pack_id and sha(goldfile) == gold_hash,
                "mutated inputs at arm exit",
            )
            raw = json.loads(rawpath.read_bytes())
            key = verify(raw, mode, case, gold, pack_id, r["scope_membership"])
            need(key == expected.setdefault(case, key), "cross-arm mismatch: " + case)
            r["arms"][label] = {
                "raw_sha256": sha(rawpath),
                "invariant_sha256": key,
                "native": raw["native"],
                "phases": raw["phases"],
                "proof_scan_DIO_bytes": 6 * STRIDE,
                "dump_verification_bytes": 2 * 40 * 3 * SLAB if case == "success" else 0,
                "native_maxrss_kib": raw["maxrss_KiB"],
            }

        if args.phase != "candidate":
            exe, r["builds"]["original"] = compile_fixture(
                out / "original-src", "original", base_dso, crypto, out, run
            )
            arm(exe, "original", "DENSE", "success")
        if args.phase != "original":
            delta = extract(backend, out / "patched-src")
            need(delta == r["c291"]["blobs"], "baseline and patched input tree must match")
            r["runtime_delta_sha256"] = apply_runtime(patch, out / "patched-src", run)
            exe, r["builds"]["candidate"] = compile_fixture(
                out / "patched-src", "candidate", base_dso, crypto, out, run
            )
            for mode, case in CASES:
                arm(exe, "candidate", mode, case)
        n = {"full": 12, "original": 1, "candidate": 11}[args.phase]
        need(len(r["arms"]) == n and time.monotonic() <= deadline, "incomplete/late family")
        need(sha(goldfile) == gold_hash and identity(pack) == pack_id, "cleanup identity changed")
        need(
            {p.name for p in nvme.iterdir()} == {"experts.pack", "gold.json"},
            "cleanup refuses unexpected entries",
        )
        r["scope_after"] = observe()
        pack.unlink()
        goldfile.unlink()
        nvme.rmdir()
        r["generated_input_cleanup"] = True
        r["status"] = (
            "PASS_ORIGINAL_DENSE"
            if args.phase == "original"
            else "PASS_C291_SYNTHETIC_WORKER_FAMILY"
        )
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
        RuntimeError,
    ) as error:
        r["error"] = type(error).__name__ + ": " + str(error)
    finally:
        signal.alarm(0)
        r["finished_utc"], r["total_wall_s"] = utc(), round(time.monotonic() - start, 6)
        r["combined_active_wall_s"] = round(r["total_wall_s"] + r.get("prior_wall_s", 0), 6)
        publish(out, r)
    return 0 if r["status"].startswith("PASS") else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("backend", "new-output", "new-nvme-dir"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--base-dso", type=Path)
    parser.add_argument("--crypto", type=Path, default=Path("/usr/lib64/libcrypto.so.3"))
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--scope-unit", required=True)
    parser.add_argument("--phase", choices=("full", "original", "candidate"), default="full")
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--original-receipt", type=Path)
    parser.add_argument("--original-sha256")
    raise SystemExit(run_campaign(parser.parse_args()))
