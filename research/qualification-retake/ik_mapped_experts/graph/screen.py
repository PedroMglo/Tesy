"""Frozen scheduler fixture for the ik CPU DSO. No model or GPU dependency."""

import argparse
import collections
import hashlib
import json
import os
import resource
import struct
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "7a5d90009b7ae55d3239cdd33244977c4eb10ff6"
TREE = "a1706c85dc11d32b0fc34e20d699066a88b56201"
LIB = "5395348a4bffef748be95e7657cbd25dd2ceaaa50f4f00e0f9d58dc742329c0c"
STRIDE = 17408
CHUNK = 2 * 1024 * 1024
PICKS = ((0, 1, 63, 127), (2, 3, 61, 125))
MODES = ("off", "default", "zero")
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "OMP_NUM_THREADS": "1", "MALLOC_ARENA_MAX": "1"}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write(path, data):
    with path.open("x") as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def output(cmd):
    return subprocess.check_output(cmd, env=ENV, text=True).strip()


def versions(a):
    actual = output(["git", "-C", a.source, "rev-parse", "HEAD", "HEAD^{tree}"]).splitlines()
    check(actual == [PIN, TREE], "wrong ik revision")
    check(not output(["git", "-C", a.source, "status", "--porcelain"]), "dirty ik")
    check(sha(a.lib) == LIB, "R03 GGML identity")
    cfg = (a.lib.parents[2] / "CMakeCache.txt").read_text().splitlines()
    for setting in (
        f"CMAKE_HOME_DIRECTORY:INTERNAL={a.source.resolve()}",
        "GGML_CUDA:BOOL=OFF",
        "GGML_IQK_MUL_MAT:BOOL=ON",
    ):
        check(setting in cfg, "upstream build configuration")
    files = ("protocol.md", "graph.cpp", "screen.py", "test_screen.py")
    path = "research/qualification-retake/ik_mapped_experts/graph/"
    for name in files:
        sealed = subprocess.check_output(
            ["git", "-C", a.repo, "show", f"{a.revision}:{path}{name}"]
        )
        check(sealed == (HERE / name).read_bytes(), f"source drift: {name}")
    return {name: sha(HERE / name) for name in files}


def build(a, out):
    sources = versions(a)
    binary = out / "ik-graph"
    cmd = [
        "/usr/bin/c++",
        "-std=c++17",
        "-O1",
        "-pthread",
        "-Wl,--export-dynamic",
        "-I" + str(a.source / "ggml/include"),
        "-I" + str(a.source / "ggml/src"),
        str(HERE / "graph.cpp"),
        str(a.lib),
        "-Wl,-rpath," + str(a.lib.parent),
        "-ldl",
        "-o",
        str(binary),
    ]
    with (out / "compiler.log").open("xb") as f:
        subprocess.run(cmd, env=ENV, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=120)
    ldd = output(["ldd", "-r", binary])
    check("undefined symbol:" not in ldd and "not found" not in ldd, "unclosed ELF")
    paths = [
        s.split("=>", 1)[1].strip().split()[0] for s in ldd.splitlines() if "libggml.so =>" in s
    ]
    check(len(paths) == 1 and Path(paths[0]).resolve() == a.lib.resolve(), "GGML provider")
    (out / "loader.txt").write_text(ldd + "\n")
    return {
        "status": "PASS_BUILD",
        "revision": a.revision,
        "sources": sources,
        "ik_commit": PIN,
        "ik_tree": TREE,
        "library_sha256": LIB,
        "binary_sha256": sha(binary),
        "compiler_sha256": sha(Path(cmd[0])),
        "loader_sha256": sha(out / "loader.txt"),
    }


def offsets(path):
    roles = ("gate", "up", "down")
    bases = []
    with path.open("rb") as f:
        check(f.read(24) == struct.pack("<4sIQQ", b"GGUF", 3, 6, 0), "GGUF header")
        for j in range(6):
            (size,) = struct.unpack("<Q", f.read(8))
            check(
                size < 64
                and f.read(size).decode() == f"blk.{j // 3}.ffn_{roles[j % 3]}_exps.weight",
                "GGUF name",
            )
            dims, x, y, e, kind, off = struct.unpack("<IQQQIQ", f.read(40))
            check(
                (dims, x, y, e, kind)
                == (3, 256 if j % 3 == 2 else 128, 128 if j % 3 == 2 else 256, 128, 39),
                "GGUF geometry",
            )
            check(off == j * 128 * STRIDE, "GGUF relative offset")
            bases.append(off)
        base = (f.tell() + 31) // 32 * 32
    check(path.stat().st_size == base + 6 * STRIDE * 128 and base % 4096, "GGUF extent/alignment")
    return [base + v for v in bases]


def expected(base, ids):
    groups = []
    for expert in sorted(set(ids)):
        if groups and groups[-1][1] == expert:
            groups[-1][1] += 1
        else:
            groups.append([expert, expert + 1])
    chunks = []
    for a, b in groups:
        end = base + b * STRIDE
        for start in range(base + a * STRIDE, end, CHUNK):
            lo = start // 4096 * 4096
            chunks.append((lo, min(start + CHUNK, end) - lo))
    return sorted(chunks)


def classify(rows, base, ids):
    options = {"none": [], "selected": expected(base, ids), "full": expected(base, range(128))}
    for label, pattern in options.items():
        if sorted(rows) == pattern:
            return label
    raise ValueError(f"unexplained worker intervals at tensor offset {base}: {rows}")


def union_pages(spans):
    pages = set()
    for off, size in spans:
        pages.update(range(off // 4096, (off + size + 4095) // 4096))
    return len(pages) * 4096


def output_rows(data, layout, pos, perm=False):
    layers = 1 if layout == 0 else 2
    cursor = 0
    outputs = []
    for layer in range(layers):
        ids = tuple(PICKS[layer][r ^ 1 if perm else r] for r in range(4))
        check(data[cursor : cursor + pos * 16] == struct.pack("<4i", *ids) * pos, "computed top-k")
        cursor += pos * 16
        nbytes = pos * 4 * 128 * 4
        part = data[cursor : cursor + nbytes]
        check(len(part) == nbytes, "incomplete F32 output")
        for (word,) in struct.iter_unpack("<I", part):
            check(word & 0x7F800000 != 0x7F800000, "nonfinite down")
        outputs.append(part)
        cursor += nbytes
    check(cursor == len(data), "trailing bytes")
    return outputs


def permutation(base, other):
    for i in range(0, len(base), 4 * 512):
        group = [base[i + r * 512 : i + (r + 1) * 512] for r in range(4)]
        check(len(set(group)) == 4, "rank-insensitive control")
        check(
            other[i : i + 4 * 512] == b"".join(group[r ^ 1] for r in range(4)),
            "wrong expert/rank result",
        )


def analyse(directory, mode, bases, reference):
    events = {}
    declared, splits = {}, {}
    pool = rss = key = None
    for row in (directory / "stdout").read_text().splitlines():
        t = row.split()
        if not t:
            continue
        if t[0] == "weight":
            j, off, stride = map(int, t[1:])
            check(j not in declared and stride == STRIDE, "native weight")
            declared[j] = off
        elif t[0] == "case":
            key = t[1]
            check(key not in events, "duplicated case")
            events[key] = []
            splits[key] = int(t[2])
        elif t[0] in {"F", "S", "H", "K", "M", "!"}:
            check(key is not None, "events outside case")
            events[key].append((t[0], *map(int, t[1:])))
        elif t[0] == "workers":
            pool = int(t[1])
        elif t[0] == "rss_kib":
            rss = int(t[1])
    keys = {f"{layout}-{p}" for layout in range(3) for p in (1, 5, 20, 32)} | {"0-5-perm"}
    check(set(events) == keys and declared == dict(enumerate(bases)), "loader or case inventory")
    check(pool == (0 if mode == "off" else 4) and 0 < rss <= 256 * 1024, "pool/resource")
    results = {}
    for key in sorted(events):
        layout, pos = map(int, key.split("-")[:2])
        count = 3 if layout == 0 else 6
        check(splits[key] == (2 if layout == 2 else 1), "wrong observed CPU splits")
        mm = [[] for _ in range(count)]
        calls = [collections.Counter() for _ in range(count)]
        for t, j, off, size in events[key]:
            if t == "M":
                # sys_mincore receives the page-rounded start and actual (unrounded) end.
                j = (off + size - 1 - bases[0]) // (128 * STRIDE)
                check(0 <= j < count and off >= bases[j] // 4096 * 4096, "out-of-tensor mincore")
                mm[j].append((off, size))
            else:
                check(t != "!" and 0 <= j < count and off == size == 0, "API or mincore error")
                calls[j][t] += 1
        labels = [classify(mm[j], bases[j], PICKS[j // 3]) for j in range(count)]
        target = (
            "none"
            if mode == "off"
            else "full"
            if mode == "default" and pos == 32 and layout != 1
            else "selected"
        )
        for j, c in enumerate(calls):
            check(
                c.get("H", 0) == int(mode != "off") and c.get("K", 0) == int(mode != "off"),
                "kernel witness",
            )
            check(
                c.get("S", 0) == 0 and c.get("F", 0) == int(target == "full"), "scheduler dispatch"
            )
            check(labels[j] == target, f"{mode}/{key}: {labels}")
        data = (directory / (key + ".bin")).read_bytes()
        parts = output_rows(data, layout, pos, key.endswith("perm"))
        if mode != "off":
            check(data == (reference / (key + ".bin")).read_bytes(), "OFF/ON numeric mismatch")
        if key.endswith("perm"):
            orig = output_rows((directory / "0-5.bin").read_bytes(), 0, 5)
            permutation(orig[0], parts[0])
        spans = [span for role in mm for span in role]
        results[key] = {
            "n_splits": splits[key],
            "classification": labels,
            "api_by_role": [dict(c) for c in calls],
            "mincore_chunks": len(spans),
            "union_pages_bytes": union_pages(spans),
            "sum_pages_bytes": sum((size + 4095) // 4096 * 4096 for _, size in spans),
            "output_sha256": hashlib.sha256(data).hexdigest(),
            "positions": pos,
            "layers": count // 3,
        }
    return results, rss


def child(argv, out, env, deadline):
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (40, 40))

    with (out / "stdout").open("xb") as f, (out / "stderr").open("xb") as e:
        subprocess.run(
            argv,
            env=env,
            preexec_fn=limits,
            stdout=f,
            stderr=e,
            check=True,
            timeout=max(0.01, deadline - time.monotonic()),
        )


def measure(a, out):
    sources = versions(a)
    report = a.build / "receipt.json"
    b = json.loads(report.read_bytes())
    binary = a.build / "ik-graph"
    check(
        sha(report) == a.build_sha256
        and b["status"] == "PASS_BUILD"
        and b["sources"] == sources
        and b["revision"] == a.revision
        and sha(binary) == b["binary_sha256"]
        and b["library_sha256"] == LIB,
        "build identity",
    )
    check(
        a.lib.resolve()
        in [
            Path(line.split("=>", 1)[1].split()[0]).resolve()
            for line in output(["ldd", binary]).splitlines()
            if "libggml.so =>" in line
        ],
        "runtime DSO",
    )
    deadline = time.monotonic() + 60
    f = out / "fixture.gguf"
    gen = out / "generator"
    gen.mkdir()
    child([binary, "make", f], gen, ENV, deadline)
    bases = offsets(f)
    rss, cases = {}, {}
    for mode in MODES:
        d = out / mode
        d.mkdir()
        env = dict(ENV)
        if mode == "zero":
            env["GGML_MOE_PREFETCH_AHEAD"] = "0"
        child([binary, "off" if mode == "off" else "on", f, d], d, env, deadline)
        cases[mode], rss[mode] = analyse(d, mode, bases, out / "off")
    result = {
        "status": "PASS_IK_CPU_SCHEDULER_SYNTHETIC",
        "revision": a.revision,
        "ik_commit": PIN,
        "library_sha256": LIB,
        "binary_sha256": sha(binary),
        "build_sha256": a.build_sha256,
        "gguf_sha256": sha(f),
        "bases": bases,
        "cases": cases,
        "workers_off_on": [0, 4],
        "model_forwards": 0,
        "gpu_used": False,
    }
    check(time.monotonic() <= deadline, "wall budget")
    write(
        out / "cost.json",
        {"peak_rss_kib_by_mode": rss, "wall_s": 60 - (deadline - time.monotonic())},
    )
    check(
        sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
        + len(json.dumps(result, indent=2))
        + 1024
        < 16 * 1024**2,
        "family raw cap",
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("build", "run"))
    for arg in ("source", "lib", "repo", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--build", type=Path)
    p.add_argument("--build-sha256")
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(exist_ok=False, mode=0o700)
    try:
        result = build(a, out) if a.command == "build" else measure(a, out)
    except Exception as e:
        write(
            out / "receipt.json",
            {"status": "FAIL_PRESERVED", "reason": str(e), "revision": a.revision},
        )
        raise
    write(out / "receipt.json", result)
    print(result["status"], sha(out / "receipt.json"))


if __name__ == "__main__":
    os.umask(0o077)
    main()
