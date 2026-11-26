"""Verify the shadow observer using a synthetic fixture and optional isolated C294 compilation."""

import argparse
import hashlib
import json
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from journal import records, summarize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
C294 = REPO / "results/c294-feature-ready-service-window-20261006"
PIN = "237e3b8789650fd68b97641c5b8e259d198ed3b1"
TREE = "149078c009a40b2c69ee126cdb84091fe3e95606"
LIMIT = 4 * 1024**2


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def clamp():
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def tree_rss(pid):
    root = Path("/proc") / str(pid)
    try:
        data = (root / "status").read_text()
        rss = next((int(s.split()[1]) for s in data.splitlines() if s.startswith("VmRSS:")), 0)
        children = (root / "task" / str(pid) / "children").read_text().split()
    except (FileNotFoundError, ProcessLookupError):
        return 0
    return rss + sum(tree_rss(int(child)) for child in children)


def disk(root):
    return sum(p.stat().st_size for p in root.rglob("*") if not p.is_symlink() and p.is_file())


def run(root, results, tag, cmd, aliases):
    start = time.monotonic()
    cmd = list(map(str, cmd))
    log = root / (tag + ".log")
    with (
        log.open("xb") as stream,
        subprocess.Popen(
            cmd, cwd=root, stdout=stream, stderr=stream, start_new_session=True, preexec_fn=clamp
        ) as proc,
    ):
        peak = 0
        stopped = None
        while proc.poll() is None:
            peak = max(peak, tree_rss(proc.pid))
            if peak > 512 * 1024 or time.monotonic() - start > 90 or disk(root) > LIMIT:
                stopped = "RESOURCE_LIMIT"
                os.killpg(proc.pid, signal.SIGKILL)
                break
            time.sleep(0.03)
        code = proc.wait()

    def sanitized(s):
        for path, label in aliases:
            s = s.replace(str(path), label)
        return s

    result = {
        "stage": tag,
        "command": [sanitized(s) for s in cmd],
        "returncode": code,
        "wall_s": round(time.monotonic() - start, 3),
        "tree_peak_rss_kib_sampled": peak,
        "stop": stopped,
        "log": sanitized(log.read_text(errors="replace")[:1500]),
    }
    results.append(result)
    return code == 0 and stopped is None and disk(root) <= LIMIT


def crosscheck(raw):
    # Freeze a genuinely separate schedule. No route callback or writer constructs these rows.
    expected = []
    schedule = [
        (1, 1, list(range(32)), []),
        (1, 2, [32], [32]),
        (2, 1, [33, 34, 35], [33, 35]),
        (3, 1, [36], [36]),
    ]
    for call, ub, positions, output in schedule:
        for layer in range(36):
            active = positions if layer < 35 else output
            if not active:
                expected.append(("pruned", call, ub, 35))
            for pos in active:
                ids = tuple((4 * pos + 5 * layer + offset) % 128 for offset in (11, 3, 17, 1))
                expected.append(
                    ("row", call, ub, layer, pos, "M" if len(active) > 10 else "S", ids)
                )
        if (call, ub) in ((1, 2), (2, 1)):
            expected.append(("cut", "P" if call == 1 else "I", call))
    observed = list(records(raw))
    require(observed == expected, "fixture differs from ordered independent reference")
    require(
        len({e for r in observed if r[:4] == ("row", 1, 1, 0) for e in r[-1]}) > 40,
        "multi-wave fixture does not exceed capacity",
    )
    for invalid in [raw[:-1], raw + b"X", raw.replace(b"ZE", b"EE", 1)]:
        require(invalid != raw, "negative fixture unchanged")
        try:
            list(records(invalid))
        except ValueError:
            continue
        raise ValueError("invalid journal accepted")
    return summarize(raw)


def fixture(root, results, aliases):
    exe = root / "fixture"
    require(
        run(
            root,
            results,
            "fixture-build",
            [
                "c++",
                "-std=c++17",
                "-O1",
                "-g0",
                "-ffile-prefix-map=" + str(root) + "=/tesy-build",
                "-ffile-prefix-map=" + str(REPO) + "=/tesy-project",
                "-pipe",
                "-Wall",
                "-Wextra",
                "-Werror",
                HERE / "fixture.cpp",
                "-o",
                exe,
            ],
            aliases,
        ),
        "fixture build failed",
    )
    require(
        run(root, results, "fixture-run", [exe, root / "fixture.bin"], aliases), "fixture failed"
    )
    return dict(crosscheck((root / "fixture.bin").read_bytes()), executable_sha256=sha(exe))


def project(root, backend, results, aliases, facts):
    git = ["git", "-C", str(backend)]

    def rev(*args):
        return subprocess.check_output([*git, *args], text=True).strip()

    require(
        rev("rev-parse", "HEAD") == PIN and rev("rev-parse", "HEAD^{tree}") == TREE, "pin mismatch"
    )
    paths = ["src", "include", "ggml/include", "vendor/nlohmann"]
    require(not rev("status", "--porcelain", "--", *paths), "modified backend headers or sources")
    prot = json.loads((C294 / "protocol.json").read_bytes())
    require(prot["backend_commit"] == PIN and prot["backend_tree"] == TREE, "protocol pin mismatch")
    (root / "src").mkdir()
    (root / "tools").mkdir()
    modified = ["llama-context.cpp", "llama-moe-stream.cpp", "llama-moe-stream.h"]
    for name in modified:
        shutil.copyfile(backend / "src" / name, root / "src" / name)
    for h in (backend / "src").glob("*.h"):
        dst = root / "src" / h.name
        if not dst.exists():
            dst.symlink_to(h)
    shutil.copyfile(HERE / "prefix_routes.h", root / "src/prefix_routes.h")
    client = REPO / "tools/expert_service_window.cpp"
    expected = next(
        v for k, v in prot["file_sha256"].items() if k.endswith("/tools/expert_service_window.cpp")
    )
    require(sha(client) == expected, "C294 harness source changed")
    shutil.copyfile(client, root / "tools" / client.name)
    for tag in ["backend", "harness"]:
        require(
            run(
                root,
                results,
                "apply-" + tag,
                ["git", "apply", "--no-index", HERE / (tag + ".patch")],
                aliases,
            ),
            "patch failed",
        )
    flags = [
        "-std=gnu++17",
        "-O1",
        "-g0",
        "-pipe",
        "-fPIC",
        "-ffile-prefix-map=" + str(root) + "=/tesy-build",
        "-ffile-prefix-map=" + str(REPO) + "=/tesy-project",
        "-ffile-prefix-map=" + str(backend) + "=/tesy-backend",
        "-DNDEBUG",
        "-DGGML_BACKEND_SHARED",
        "-DGGML_SHARED",
        "-DGGML_USE_CPU",
        "-DGGML_USE_CUDA",
        "-DLLAMA_SHARED",
        "-I" + str(root / "src"),
        "-I" + str(backend / "src"),
        "-I" + str(backend / "include"),
        "-isystem",
        str(backend / "ggml" / "include"),
    ]
    for file in [*modified[:2], client.name]:
        engine = file != client.name
        common = [
            *flags,
            *(
                ["-DLLAMA_BUILD", "-DTESY_C47_CPU_SKIP_PARKED", "-Dllama_EXPORTS"]
                if engine
                else ["-I" + str(REPO / "tools"), "-I" + str(backend / "vendor/nlohmann")]
            ),
        ]
        # Emit the two backend objects for identity; assemble the client without storing its object.
        obj = root / (file + ".o") if engine else Path(os.devnull)
        source = root / ("src" if engine else "tools") / file
        success = run(
            root, results, "object-" + file, ["c++", *common, "-c", source, "-o", obj], aliases
        )
        if success:
            facts[file] = {"status": "COMPILED_OBJECT"}
            if engine:
                facts[file].update(sha256=sha(obj), size=obj.stat().st_size)
            else:
                facts[file]["object_output"] = "discarded after assembly"
        else:
            facts[file] = {"status": "FAIL_OBJECT"}
            if run(
                root, results, "syntax-" + file, ["c++", *common, "-fsyntax-only", source], aliases
            ):
                facts[file]["fallback"] = "SYNTAX_ONLY"
    return all(f["status"] == "COMPILED_OBJECT" for f in facts.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path)
    ap.add_argument("--compare-receipt", type=Path)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    args = ap.parse_args()
    if args.compare_receipt and not args.backend:
        ap.error("a backend comparison requires --backend")
    args.new_output_dir.mkdir()
    facts = {}
    results = []
    files = [
        "protocol.md",
        "reproducibility.md",
        "prefix_routes.h",
        "fixture.cpp",
        "journal.py",
        "backend.patch",
        "harness.patch",
        "verify.py",
    ]
    report = {
        "schema": "tesy-prefix-observer-v1",
        "source_sha256": {f: sha(HERE / f) for f in files},
        "backend_pin": PIN,
        "backend_tree": TREE,
        "stages": results,
        "objects": facts,
        "compiler": subprocess.check_output(["c++", "--version"], text=True).splitlines()[0],
        "real_routes": "NOT_RUN_PHYSICAL_ADMISSION_REQUIRED",
        "integrated_off_on": "NOT_RUN_PHYSICAL_ADMISSION_REQUIRED",
    }
    with tempfile.TemporaryDirectory(prefix="tesy-route-fixture-") as tmp:
        root = Path(tmp)
        aliases = [(root, "$WORK"), (HERE, "$OBSERVER"), (REPO, "$TESY")]
        try:
            report["synthetic_fixture"] = fixture(root, results, aliases)
            if args.backend:
                backend = args.backend.resolve()
                aliases.insert(0, (backend, "$C294_BACKEND"))
                success = project(root, backend, results, aliases, facts)
                report["status"] = "PASS_MODEL_FREE" if success else "PARTIAL_MODEL_FREE"
                if args.compare_receipt:
                    prior = json.loads(args.compare_receipt.read_bytes())
                    require(
                        success and prior.get("status") == "PASS_MODEL_FREE",
                        "both builds must have completed successfully",
                    )
                    for key in (
                        "backend_pin",
                        "backend_tree",
                        "source_sha256",
                        "compiler",
                        "objects",
                        "synthetic_fixture",
                    ):
                        require(
                            prior.get(key) == report[key], "independent build differed in " + key
                        )
                    require(
                        [s["command"] for s in prior["stages"]] == [s["command"] for s in results],
                        "build commands differ",
                    )
                    report["reproduction"] = {
                        "status": "MATCH",
                        "prior_receipt_sha256": sha(args.compare_receipt),
                        "compared_backend_objects": 2,
                        "fixture_executable_and_journal_match": True,
                        "prior_workspace_regular_bytes": prior["workspace_regular_bytes"],
                    }
            else:
                report["status"] = "PASS_FIXTURE_ONLY"
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            report.update(status="FAIL", failure=type(e).__name__ + ":" + str(e))
        report["workspace_regular_bytes"] = disk(root)
    staging = args.new_output_dir / ".pending"
    with staging.open("x") as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write("\n")
    staging.replace(args.new_output_dir / "receipt.json")
    print(report["status"])
    return int(report["status"] not in ("PASS_MODEL_FREE", "PASS_FIXTURE_ONLY"))


if __name__ == "__main__":
    raise SystemExit(main())
