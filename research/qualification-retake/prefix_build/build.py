"""Build and exercise the C294 observer without a model in a new private workspace."""

import argparse
import hashlib
import json
import os
import resource
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OBSERVER = HERE.parent / "prefix_observer"
C294 = REPO / "results/c294-feature-ready-service-window-20261006/protocol.json"
C294_SHA256 = "ac8c25f5a38313e75d4fbb25ba15908be16a350e733582e46ef11eb17b6b2c6e"
PIN = "237e3b8789650fd68b97641c5b8e259d198ed3b1"
TREE = "149078c009a40b2c69ee126cdb84091fe3e95606"
GGML = {"libggml", "libggml-base", "libggml-cpu", "libggml-cuda"}
GIB = 1024**3


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def dump(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def disk(root):
    total = 0
    for path in root.rglob("*"):
        try:
            entry = path.lstat()
        except FileNotFoundError:  # Compiler scratch may disappear between directory visits.
            continue
        if stat.S_ISREG(entry.st_mode):
            total += entry.st_size
    return total


def rss(pid):
    d = Path("/proc") / str(pid)
    try:
        s = (d / "status").read_text()
        value = next(
            (int(line.split()[1]) for line in s.splitlines() if line.startswith("VmRSS:")), 0
        )
        children = (d / "task" / str(pid) / "children").read_text().split()
    except (ProcessLookupError, FileNotFoundError):
        return 0
    return value + sum(rss(int(c)) for c in children)


class Campaign:
    def __init__(self, work, backend, bins):
        self.work = work
        self.backend = backend
        self.bins = bins
        self.start = time.monotonic()
        self.commands = []
        self.max_rss = 0
        self.max_disk = 0
        self.aliases = [
            (work, "$BUILD"),
            (backend, "$C294_BACKEND"),
            (bins, "$GGML_BIN"),
            (REPO, "$TESY"),
        ]
        self.env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "TMPDIR": str(work / "tmp"),
            "CUDA_VISIBLE_DEVICES": "",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
        }

    def clean(self, s):
        for path, label in self.aliases:
            s = s.replace(str(path), label)
        return s

    def run(self, tag, argv, cwd=None, mode=None, expected=0):
        argv = list(map(str, argv))
        env = self.env if mode is None else dict(self.env, TESY_PREFIX_ROUTE_AUDIT=mode)
        stdout, stderr = (self.work / "logs" / (tag + x) for x in (".stdout", ".stderr"))
        start = time.monotonic()
        peak = 0
        abort = None
        next_disk = 0

        def clamp():
            resource.setrlimit(resource.RLIMIT_FSIZE, (GIB, GIB))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        with (
            stdout.open("xb") as out,
            stderr.open("xb") as err,
            subprocess.Popen(
                argv,
                cwd=cwd or self.work,
                env=env,
                stdout=out,
                stderr=err,
                start_new_session=True,
                preexec_fn=clamp,
            ) as p,
        ):
            while p.poll() is None:
                now = time.monotonic()
                peak = max(peak, rss(p.pid))
                if now >= next_disk:
                    self.max_disk = max(self.max_disk, disk(self.work))
                    next_disk = now + 2
                if now - self.start > 600 or peak > 4 * GIB // 1024 or self.max_disk > 2 * GIB:
                    abort = "RESOURCE_LIMIT"
                    os.killpg(p.pid, signal.SIGKILL)
                    break
                time.sleep(0.1 if tag == "compile-all" else 0.02)
            rc = p.wait()
        self.max_rss = max(self.max_rss, peak)
        self.max_disk = max(self.max_disk, disk(self.work))
        self.commands.append(
            {
                "stage": tag,
                "argv": [self.clean(a) for a in argv],
                "cwd": self.clean(str(cwd or self.work)),
                "observer_option": mode,
                "returncode": rc,
                "expected_returncode": expected,
                "stop": abort,
                "tree_peak_rss_kib_sampled": peak,
                "elapsed_s": round(time.monotonic() - start, 3),
                "stdout_sha256": sha(stdout),
                "stderr_sha256": sha(stderr),
            }
        )
        if (
            rc != expected
            or abort
            or self.max_disk > 2 * GIB
            or time.monotonic() - self.start > 600
        ):
            raise ValueError("stage failed: " + tag)
        return stdout


def inputs(proto):
    return {
        Path(key).name: (Path(key), expected)
        for key, expected in proto["binary_libraries"].items()
        if Path(key).name.split(".so")[0] in GGML
    }


def sealed_imports(bins, original):
    hashes = {}
    for name, (_, expected) in original.items():
        p = (bins / name).resolve(strict=True)
        alias = (bins / (name.split(".so")[0] + ".so")).resolve(strict=True)
        require(alias == p and p.parent == bins and sha(p) == expected, "GGML identity mismatch")
        hashes[name] = expected
    require(len(hashes) == 4, "missing GGML input")
    return hashes


def frozen_copy(src, dst, manifest):
    expected = [
        v for k, v in manifest.items() if k.endswith("/" + src.relative_to(REPO).as_posix())
    ]
    require(len(expected) == 1 and sha(src) == expected[0], "historical Tesy source changed")
    shutil.copyfile(src, dst)
    return expected[0]


def map_objects(names, work, bins, import_hashes):
    actual = {}
    for name in names:
        if name == "linux-vdso.so.1":
            continue
        p = Path(name).resolve(strict=True)
        require(p.name not in actual, "duplicate resolved basename")
        if p.name.startswith("libllama"):
            require(p == (work / "cmake/bin/libllama.so.0.0.9884"), "external llama DSO")
        if p.name.startswith("libggml"):
            require(p.parent == bins and p.name in import_hashes, "unexpected GGML DSO")
        actual[p.name] = sha(p)
    require(all(actual.get(k) == h for k, h in import_hashes.items()), "mapped GGML differs")
    require(
        actual.get("libllama.so.0.0.9884") == sha(work / "cmake/bin/libllama.so.0.0.9884"),
        "new private llama was not selected",
    )
    return actual


def compilation(c, r):
    w, b = c.work, c.backend
    require(sha(C294) == C294_SHA256, "historical C294 protocol changed")
    proto = json.loads(C294.read_bytes())
    require(
        proto["backend_commit"] == PIN and proto["backend_tree"] == TREE, "C294 protocol changed"
    )
    pins = inputs(proto)
    imports = sealed_imports(c.bins, pins)
    r["imported_ggml"] = imports
    rev = c.run("pin", ["git", "-C", b, "rev-parse", PIN, PIN + "^{tree}"]).read_text().splitlines()
    require(rev == [PIN, TREE], "Git source pin mismatch")
    src = w / "source"
    src.mkdir()
    c.run(
        "export",
        [
            "git",
            "-C",
            b,
            "archive",
            "--format=tar",
            "-o",
            w / "source.tar",
            PIN,
            "src",
            "include",
            "ggml/include",
            "vendor/nlohmann",
        ],
    )
    c.run("extract", ["tar", "-xf", w / "source.tar", "-C", src])
    tools = w / "project/tools"
    tools.mkdir(parents=True)
    recipe = tools / "expert_window_build"
    recipe.mkdir()
    copied = {}
    for path in [
        "tools/expert_service_window.cpp",
        "tools/block_native_run.cpp",
        "tools/expert_window_build/CMakeLists.txt",
    ]:
        copied[path] = frozen_copy(REPO / path, w / "project" / path, proto["file_sha256"])
    r["pinned_client_sources"] = copied
    observer_receipt = json.loads((OBSERVER / "reproduced/receipt.json").read_bytes())
    require(observer_receipt["reproduction"]["status"] == "MATCH", "observer revision not verified")
    for name in ["backend.patch", "harness.patch", "prefix_routes.h"]:
        require(
            sha(OBSERVER / name) == observer_receipt["source_sha256"][name],
            "observer source changed",
        )
    shutil.copyfile(OBSERVER / "prefix_routes.h", src / "src/prefix_routes.h")
    for tag, patch, root in [
        ("patch-backend", OBSERVER / "backend.patch", src),
        ("patch-client", OBSERVER / "harness.patch", w / "project"),
        ("patch-probe", HERE / "client-probe.patch", w / "project"),
    ]:
        c.run(tag, ["git", "apply", "--no-index", patch], cwd=root)
    build = w / "cmake"
    c.run(
        "configure",
        [
            "cmake",
            "-S",
            recipe,
            "-B",
            build,
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_C_COMPILER=/usr/bin/cc",
            "-DCMAKE_CXX_COMPILER=/usr/bin/c++",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            "-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON",
            "-DCMAKE_INSTALL_RPATH=$ORIGIN;" + str(c.bins),
            "-DCMAKE_CXX_FLAGS=-ffile-prefix-map=" + str(w) + "=/tesy-prefix-build -pipe",
            "-DTESY_BACKEND=" + str(src),
            "-DTESY_QUALIFIED_BIN=" + str(c.bins),
            "-DTESY_REPO=" + str(w / "project"),
        ],
    )
    db = json.loads((build / "compile_commands.json").read_bytes())
    llama = [Path(row["file"]) for row in db if Path(row["file"]).is_relative_to(src / "src")]
    client = [
        Path(row["file"]) for row in db if Path(row["file"]) == tools / "expert_service_window.cpp"
    ]
    require(
        len(db) == 167 and len(set(llama)) == 166 and len(client) == 1,
        "incomplete/cross-source TU graph",
    )
    require(
        not list((build / "llama").rglob("*.o")) and not list((build / "bin").glob("*.so*")),
        "nonempty llama build",
    )
    c.run(
        "compile-all",
        ["cmake", "--build", build, "--parallel", "4", "--target", "expert-service-window"],
    )
    objs = list((build / "llama").rglob("*.cpp.o"))
    require(len(objs) == len(llama), "not all llama objects compiled")
    deps = (
        c.run("header-dependency-closure", ["ninja", "-C", build, "-t", "deps"])
        .read_text()
        .split("\n\n")
    )
    dependent = []
    for block in deps:
        # Exact dependency line in Ninja's post-compile dep database.
        lines = block.splitlines()
        if lines and any(
            Path(line.strip()).resolve() == src / "src/llama-moe-stream.h"
            for line in lines[1:]
            if line.strip().endswith("/llama-moe-stream.h")
        ):
            dependent.append(Path(lines[0].split(": #deps", 1)[0]).name)
    expected = set(
        [
            "llama-context.cpp.o",
            "llama-graph.cpp.o",
            "llama-model.cpp.o",
            "llama-moe-stream.cpp.o",
            "expert_service_window.cpp.o",
        ]
    )
    require(expected <= set(dependent), "layout consumers absent from dependency closure")
    r["compile_graph"] = {
        "clean_llama_tus": len(objs),
        "clean_client_tus": 1,
        "cuda_compilations": 0,
        "layout_consumers": sorted(dependent),
        "source_relative_list_sha256": hashlib.sha256(
            "\n".join(sorted(str(f.relative_to(src)) for f in llama)).encode()
        ).hexdigest(),
    }
    exe = build / "bin/expert-service-window"
    r["products"] = {
        p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
        for p in [exe, build / "bin/libllama.so.0.0.9884"]
    }
    r["build_identities"] = {
        "compiler": c.run("compiler-version", ["c++", "--version"]).read_text().splitlines()[0],
        "cmake": c.run("cmake-version", ["cmake", "--version"]).read_text().splitlines()[0],
        "ninja": c.run("ninja-version", ["ninja", "--version"]).read_text().strip(),
    }
    return exe, imports


def smoke(c, r, exe, imports):
    output = c.run("elf", ["/usr/bin/readelf", "-dW", exe]).read_text()
    require("$ORIGIN" in output and "libllama.so.0" in output, "runtime search contract changed")
    linked = c.run("ldd", ["/usr/bin/ldd", exe]).read_text()
    require("not found" not in linked, "unresolved loader dependency")
    candidates = [line.split("=>", 1)[1].split()[0] for line in linked.splitlines() if "=>" in line]
    static = map_objects(candidates, c.work, c.bins, imports)
    c.run("cli-usage", [exe], expected=1)
    require(
        "usage MODEL FIXTURE CASE NEWROOT" in (c.work / "logs/cli-usage.stderr").read_text(),
        "unexpected CLI usage failure",
    )
    selftest = c.run("window-self-test", [exe, "--self-test"]).read_text()
    require(
        "PASS_MODEL_FREE_WINDOW_BOUNDS_THREADS_CALLBACK_CALLS_ROWS" in selftest,
        "missing original self-test",
    )
    summaries = []
    for tag, mode in [("prefix-default", None), ("prefix-enabled", "1")]:
        result = json.loads(c.run(tag, [exe, "--prefix-config-probe"], mode=mode).read_bytes())
        require(
            result["default_pointer_empty"] is True
            and result["enabled"] is (mode == "1")
            and result["worker_count"] == result["open_model_files"] == 0,
            "observer option mismatch",
        )
        mapped = map_objects(result.pop("mapped_objects"), c.work, c.bins, imports)
        require(
            all(mapped.get(k) == h for k, h in static.items()), "runtime mapping differs from ldd"
        )
        summaries.append(result)
        if tag == "prefix-default":
            r["startup_mapped_objects_sha256"] = mapped
        else:
            require(mapped == r["startup_mapped_objects_sha256"], "different startup DSO set")
    c.run("prefix-invalid", [exe, "--prefix-config-probe"], mode="0", expected=1)
    require(
        "invalid prefix route audit option" in (c.work / "logs/prefix-invalid.stderr").read_text(),
        "invalid option not refused",
    )
    r["startup_probes"] = summaries
    c.run(
        "independent-fixture",
        ["python3", "-B", OBSERVER / "verify.py", "--new-output-dir", c.work / "fixture"],
    )
    fixture = json.loads((c.work / "fixture/receipt.json").read_bytes())
    prior = json.loads((OBSERVER / "reproduced/receipt.json").read_bytes())["synthetic_fixture"]
    require(
        fixture["status"] == "PASS_FIXTURE_ONLY" and fixture["synthetic_fixture"] == prior,
        "model-free reference changed",
    )
    r["fixture_journal_sha256"] = prior["journal_sha256"]
    require(
        sealed_imports(c.bins, inputs(json.loads(C294.read_bytes()))) == imports, "GGML changed"
    )
    r["needed_direct"] = [
        line.split("[")[1].split("]")[0] for line in output.splitlines() if "(NEEDED)" in line
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", required=True, type=Path)
    ap.add_argument("--ggml-bin", required=True, type=Path)
    ap.add_argument("--private-workspace", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    args = ap.parse_args()
    os.umask(0o077)
    work, out = args.private_workspace.resolve(), args.new_output_dir.resolve()
    require(
        not out.is_relative_to(work) and not work.is_relative_to(args.backend.resolve()),
        "use independent private and publication roots",
    )
    out.mkdir()
    work.mkdir(mode=0o700)
    (work / "logs").mkdir()
    (work / "tmp").mkdir()
    c = Campaign(work, args.backend.resolve(), args.ggml_bin.resolve())
    r = {
        "scope": "MODEL_FREE_ELF_STARTUP",
        "fixture_and_build_sha256": {
            p.name: sha(p)
            for p in [
                HERE / "protocol.md",
                HERE / "client-probe.patch",
                Path(__file__).resolve(),
                C294,
            ]
        },
        "backend_commit": PIN,
        "backend_tree": TREE,
        "target_inference": "NOT_RUN_PHYSICAL_ADMISSION_REQUIRED",
        "integrated_neutrality": "NOT_RUN_PHYSICAL_ADMISSION_REQUIRED",
        "model_forwards": 0,
    }
    try:
        exe, imports = compilation(c, r)
        smoke(c, r, exe, imports)
        r["status"] = "PASS_LINKED_MODEL_FREE"
    except (OSError, ValueError, IndexError, KeyError, subprocess.SubprocessError) as exc:
        r.update(status="FAIL", reason=c.clean(str(exc))[:400])
    r["stages"] = c.commands
    r["resources"] = {
        "elapsed_s": round(time.monotonic() - c.start, 3),
        "process_tree_peak_rss_kib_sampled": c.max_rss,
        "private_peak_sampled_bytes": max(c.max_disk, disk(work)),
    }
    dump(work / "build-receipt.json", r)
    dump(out / ".pending", r)
    (out / ".pending").replace(out / "receipt.json")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] != "PASS_LINKED_MODEL_FREE")


if __name__ == "__main__":
    raise SystemExit(main())
