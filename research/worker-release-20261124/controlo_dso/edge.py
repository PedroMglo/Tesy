"""Check one authenticated C317 router row through the original C305 DSO on CPU."""

import argparse
import hashlib
import json
import math
import os
import resource
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "manager"), str(HERE.parent)]
import run as control  # noqa: E402
from audit import primary, require, source  # noqa: E402
from verify_result import read_slab, reference  # noqa: E402

ARM = "c317-nominal153-2-trace.native"
MANIFEST = "8181c3a8f958300033da765518bb0d27e7a52539"
PROTOCOL = "fefdf5e92c8a7fd8446a39d57fe5e73fda60e4d8"
ROW_SHA = "c2a65abc2a11c7e398e9ed0f863b2b67859ac2cd1740c7d3de4328e76361d3f2"
CONTROL_DSO = "libllama.so.0.0.9884"
SLAB, REGION = control.SLAB, control.REGION
CAP = 1280 * 1024**2


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", HERE, *args], timeout=10)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def router_row(raw_dir):
    manifest_path = source.C317 + "/raw-manifest.json"
    require(source.SOURCE_BLOBS[manifest_path] == MANIFEST, "changed raw inventory")
    manifest = source.archived(manifest_path)["files"]
    raws = {}
    pins = {}
    for name in ("true-routing-scores.f32", "events.tsv"):
        path = f"{source.C317}/raw/{ARM}/{name}"
        (row,) = [m for m in manifest if m["path"] == path]
        pins[name] = {key: row[key] for key in ("sha256", "size_bytes")}
        raws[name] = source.checked_bytes(raw_dir / ARM / name, pins[name])
    matrix = raws["true-routing-scores.f32"]
    require(len(matrix) == 32 * 23 * 128 * 4, "matrix shape")
    # activation_bank::label, inherited by the learned movement estimator.
    row_index = (1 - 1) * 23 + 4 - 2
    row = matrix[row_index * 512 : (row_index + 1) * 512]
    require(digest(row) == ROW_SHA, "true routing-score row")
    values = struct.unpack("<128f", row)
    require(all(math.isfinite(v) for v in values), "non-finite true score")
    ordered = sorted(range(128), key=values.__getitem__, reverse=True)
    require(all(values[ordered[i]] > values[ordered[i + 1]] for i in range(4)), "top rank tie")
    ranks = ordered[:4]
    events, *_ = primary(raws["events.tsv"].decode())
    layer = [e for e in events if e.call == 1 and e.layer == 4]
    hits = [
        dict(expert=e.expert, slot=e.slot, generation=e.gen, state=e.size)
        for e in layer
        if e.kind == 3
    ]
    missed = [e for e in layer if e.kind == 4]
    committed = [e for e in layer if e.kind == 10]
    require([r["expert"] for r in hits] == ranks, "P3 order differs from true top four")
    require(
        [r["expert"] for r in hits if r["state"] == 0] == [e.expert for e in missed]
        and [e.work for e in missed] == [e.work for e in committed],
        "P4/P10 population",
    )
    return (
        row,
        ranks,
        {
            "arm": ARM,
            "call": 1,
            "layer": 4,
            "row_index_zero_based": row_index,
            "row_sha256": ROW_SHA,
            "sources": pins,
            "historical_P3": hits,
            "historical_P4": [dict(expert=e.expert, slot=e.slot, generation=e.gen) for e in missed],
            "ranks": ranks,
        },
    )


def make_source(path, ranks):
    with path.open("xb") as f:
        f.truncate(3 * REGION + 4096)
        for k in range(3):
            for expert in ranks:
                block = bytes((expert * 29 + k * 61 + (j % 251) * 11) & 255 for j in range(251))
                f.seek(k * REGION + expert * SLAB)
                f.write((block * ((SLAB + 250) // 251))[:SLAB])
        f.flush()
        os.fsync(f.fileno())
    path.chmod(0o444)
    st = path.stat()
    require(
        st.st_blocks * 512 < 64 * 1024**2 and st.st_size == 3 * REGION + 4096,
        "synthetic sparse input",
    )
    return {
        "apparent_bytes": st.st_size,
        "allocated_bytes": st.st_blocks * 512,
        "written_slabs": 12,
    }


def verify_raw(raw, arm, ranks, libraries):
    require(raw["ranks"] == ranks and raw["slots"] == list(range(4)), "scheduler ranks or slots")
    require([raw[k] for k in ("n_calls", "n_miss", "n_hit")] == [1, 4, 0], "demand population")
    expected = {
        "workers": 4,
        "queue": 0,
        "claimed": 0,
        "load_failed": False,
        "direct_primary": True,
        "joins": 4,
    }
    require(all(raw["terminal"].get(k) == v for k, v in expected.items()), "terminal manager")
    expected = {
        "backend": "CPU",
        "ops": ["ARGSORT", "VIEW", "CONT", "MAP_CUSTOM1"],
        "top_k": 4,
        "score_shape": [128, 1],
        "id_shape": [4, 1],
        "remap_tasks": 1,
    }
    require(
        all(raw["scheduler"].get(k) == v for k, v in expected.items()),
        "operator geometry or placement",
    )
    rows = raw["destinations"]
    require(len(rows) == 4, "four measured destinations")
    seen = set()
    hashes = []
    for slot, (expert, dest) in enumerate(zip(ranks, rows, strict=True)):
        require(
            (dest["expert"], dest["slot"], dest["generation"]) == (expert, slot, 1), "slot identity"
        )
        require(len(dest["files"]) == 3, "component population")
        parts = []
        for k, name in enumerate(dest["files"]):
            require(
                Path(name).name == name and name.endswith(".bin.gz") and name not in seen,
                "invalid destination artifact",
            )
            seen.add(name)
            observed = read_slab(arm / name)
            require(observed == reference(expert, k), "wrong bytes in selected rank")
            parts.append(observed)
        hashes.append(
            {"rank": slot, "expert": expert, "slot": slot, "generation": 1, "components": parts}
        )
    mapped = {}
    for value in raw["mapped_dsos"]:
        path = Path(value)
        require(path.is_absolute() and path.is_file(), "unreadable mapped image")
        path = path.resolve()
        if path.name in mapped:
            require(path == mapped[path.name], "ambiguous mapped basename")
        mapped[path.name] = path
    target = {n for n in mapped if n.startswith(("libggml", "libllama"))}
    require(target == set(libraries), "loaded a different set of GGML/llama images")
    for name, (path, expected_hash) in libraries.items():
        require(
            mapped[name].samefile(path) and control.sha(mapped[name]) == expected_hash,
            "mapped runtime image does not match its historical identity",
        )
    require(Path(raw["remap_symbol_dso"]).samefile(libraries[CONTROL_DSO][0]), "callback DSO")
    require(any(n.startswith("ld-linux-") for n in mapped), "dynamic loader missing from map")
    return {
        "destinations": hashes,
        "scheduler": raw["scheduler"],
        "terminal": raw["terminal"],
        "mapped_images_sha256": {n: control.sha(p) for n, p in sorted(mapped.items())},
    }


def run_edge(argv, out, env):
    # DT_NEEDED maps libcuda, cuBLAS and cuBLASLt even for a CPU scheduler.
    # Their file-backed address ranges are not RSS. Check resident peak and
    # enforce a separate heap limit without imposing the compile-time AS cap.
    def limits():
        resource.setrlimit(resource.RLIMIT_DATA, (CAP, CAP))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (control.ARTIFACTS, control.ARTIFACTS))

    start = time.monotonic()
    with (out / "edge.log").open("xb") as log, (out / "edge.err").open("xb") as err:
        proc = subprocess.Popen(
            argv,
            cwd=out,
            env=env,
            preexec_fn=limits,
            stdout=log,
            stderr=err,
            start_new_session=True,
        )
        try:
            while True:
                pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
                if pid:
                    proc.returncode = os.waitstatus_to_exitcode(status)
                    break
                stat = Path(f"/proc/{proc.pid}/status").read_text()
                high = [
                    int(line.split()[1]) * 1024
                    for line in stat.splitlines()
                    if line.startswith("VmHWM:")
                ]
                require(not high or high[0] <= CAP, "native RSS limit")
                require(time.monotonic() - start < 90, "native deadline")
                time.sleep(0.01)
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            raise
    require(proc.returncode == 0, f"native process exit {proc.returncode}")
    require(usage.ru_maxrss * 1024 <= CAP, "peak RSS limit")
    return {"wall_s": round(time.monotonic() - start, 6), "max_rss_kib": usage.ru_maxrss}


def execute(args):
    out = args.new_output_dir.resolve()
    out.mkdir()
    receipt = {"schema": "tesy-original-c305-ggml-edge-v1", "status": "FAIL", "phases": {}}
    try:
        commit, tree = git("rev-parse", "HEAD", "HEAD^{tree}").decode().splitlines()
        clean = not git("status", "--porcelain=v1")
        receipt["tesy"] = {
            "commit": commit,
            "tree": tree,
            "clean": clean,
            "exploratory": args.exploratory,
        }
        require(clean or args.exploratory, "confirmation needs a clean checkout")
        receipt["unit_files"] = {
            n: control.sha(HERE / n) for n in ("protocolo.md", "edge.cpp", "edge.py")
        }
        blob = git("cat-file", "blob", PROTOCOL)
        require(
            digest(blob) == "1c7ba3b67377bf22af2280f6dfa1d09fae0f1deff70bbddfa7061ecc6d9eb4ac",
            "C317 protocol",
        )
        protocol = json.loads(blob)
        require(
            protocol["backend_commit"] == control.PIN and protocol["backend_tree"] == control.TREE,
            "C317 backend source pin",
        )
        historical = {Path(k).name: v for k, v in protocol["file_sha256"].items()}
        ggml_dir = args.ggml_dir.resolve()
        libraries = {
            n: ((args.libllama.resolve() if n == CONTROL_DSO else (ggml_dir / n).resolve()), v)
            for n, v in historical.items()
            if n == CONTROL_DSO or n.startswith("libggml")
        }
        require(
            len(libraries) == 5
            and all(p.name == n and control.sha(p) == s for n, (p, s) in libraries.items()),
            "original C317 runtime images",
        )
        row, ranks, receipt["historical_router"] = router_row(args.raw_dir)
        receipt["source"] = {
            "backend_commit": control.PIN,
            "backend_tree": control.TREE,
            "history": source.SOURCE,
            "manifest_blob": MANIFEST,
            "protocol_blob": PROTOCOL,
        }
        receipt["input"] = make_source(out / "synthetic.bin", ranks)
        (out / "selected.f32").write_bytes(row)
        private = out / "backend"
        control.checkout_sources(args.backend.resolve(), private)
        headers = sorted(private.rglob("*.h")) + sorted(private.rglob("*.hpp"))
        receipt["headers_manifest_sha256"] = digest(
            b"".join(
                str(p.relative_to(private)).encode() + b" " + control.sha(p).encode() + b"\n"
                for p in headers
            )
        )
        exe = out / "edge-bin"
        dirs = [str(args.libllama.resolve().parent), str(ggml_dir)]
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "OMP_NUM_THREADS": "1",
            "MALLOC_ARENA_MAX": "2",
            "CUDA_VISIBLE_DEVICES": "",
            "LD_LIBRARY_PATH": ":".join(dirs),
        }
        argv = [
            "/usr/bin/g++",
            "-std=c++17",
            "-O0",
            "-g0",
            "-fPIC",
            "-fno-plt",
            "-pie",
            "-pthread",
            "-Wall",
            "-Wextra",
        ]
        argv.extend(
            "-I" + str(private / p) for p in ("src", "include", "ggml/include", "vendor/nlohmann")
        )
        argv += [str(HERE / "edge.cpp"), "-Wl,-rpath-link," + str(ggml_dir)]
        argv.extend(
            str(libraries[n][0])
            for n in (
                CONTROL_DSO,
                "libggml.so.0.15.3",
                "libggml-cpu.so.0.15.3",
                "libggml-base.so.0.15.3",
            )
        )
        argv.extend(["-lz", "-o", str(exe)])
        receipt["compiler_sha256"] = control.sha(Path(argv[0]))
        receipt["phases"]["build"] = control.run_bounded(argv, out, "build", env)
        receipt["executable_sha256"] = control.sha(exe)
        arm = out / "arm"
        arm.mkdir()
        receipt["phases"]["native"] = run_edge(
            [exe, out / "selected.f32", out / "synthetic.bin", arm], out, env
        )
        raw_path = arm / "raw.json"
        receipt["raw_sha256"] = control.sha(raw_path)
        result = verify_raw(json.loads(raw_path.read_bytes()), arm, ranks, libraries)
        actual = result["mapped_images_sha256"]
        receipt["original_openmp_vs_local"] = [
            {
                "name": Path(name).name,
                "historical_sha256": old,
                "mapped_sha256": actual.get(Path(name).name),
                "identical": actual.get(Path(name).name) == old,
            }
            for name, old in protocol["parallel_runtime"]["libraries_sha256"].items()
        ]
        receipt["result"] = result
        receipt["status"] = "PASS_ORIGINAL_C305_SCHEDULER_EDGE"
    except (OSError, ValueError, KeyError, AssertionError, subprocess.SubprocessError) as exc:
        receipt["failure"] = str(exc)
    finally:
        receipt["allocated_bytes_before_receipt"] = control.tree_bytes(out)
        if receipt["allocated_bytes_before_receipt"] > control.ARTIFACTS:
            receipt.update(status="FAIL", failure="disk budget exceeded")
        part = out / "receipt.json.part"
        with part.open("x") as f:
            json.dump(receipt, f, indent=2, allow_nan=False)
            f.write("\n")
        part.rename(out / "receipt.json")
    print(receipt["status"])
    return int(receipt["status"] != "PASS_ORIGINAL_C305_SCHEDULER_EDGE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ["--backend", "--raw-dir", "--libllama", "--ggml-dir", "--new-output-dir"]:
        parser.add_argument(arg, required=True, type=Path)
    parser.add_argument("--exploratory", action="store_true")
    raise SystemExit(execute(parser.parse_args()))
