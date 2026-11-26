"""Authenticate a header-only sparse view and compare the native ik index with C283."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
WORKER = run_path(str(HERE.parent / "verify.py"))
LEGACY = run_path(str(HERE.parents[1] / "moestream_capacity.py"))
need, sha, env = (WORKER[key] for key in ("need", "sha", "ENV"))
LIBLLAMA = "aa1e18b41a8f04ed396e885f24288965a8961e611261e173774e9f9cd538b74a"
LIBGGML = "5395348a4bffef748be95e7657cbd25dd2ceaaa50f4f00e0f9d58dc742329c0c"
EXPERT = re.compile(r"blk\.\d+\.ffn_(?:gate|up|down)_exps\.(weight|bias)$")


def child(binary, header, size, mode, output):
    fd = os.memfd_create("tesy-ik-gguf-header-only", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
    try:
        os.ftruncate(fd, size)
        need(os.pwrite(fd, header, 0) == len(header), "header copy")
        seals = fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        stat = os.fstat(fd)
        page = os.sysconf("SC_PAGE_SIZE")
        need(
            stat.st_size == size
            and len(header) <= stat.st_blocks * 512 < len(header) + page
            and fcntl.fcntl(fd, fcntl.F_GET_SEALS) == seals,
            "sparse sealed metadata extent",
        )
        with (
            (output / f"{mode}.stdout").open("xb") as out,
            (output / f"{mode}.stderr").open("xb") as err,
        ):
            subprocess.run(
                ["prlimit", "--as=1073741824", "--cpu=60", binary, f"/proc/self/fd/{fd}", mode],
                pass_fds=(fd,),
                env=env,
                stdout=out,
                stderr=err,
                check=True,
                timeout=60,
            )
        return json.loads((output / f"{mode}.stdout").read_bytes()), stat.st_blocks * 512
    finally:
        os.close(fd)


def compare(native, entries):
    dtype = {"mxfp4": 39, "q8_0": 8, "f32": 0}
    rows = sorted(native["tensors"], key=lambda row: row["offset"])
    need(len(rows) == len(entries) == 687, "tensor population")
    ranges = native["ranges"]
    need(all(a < b for a, b in ranges), "empty native span")
    need(all(a[1] < b[0] for a, b in zip(ranges, ranges[1:], strict=False)), "unmerged spans")
    counts = {key: {"tensors": 0, "bytes": 0} for key in ("weight", "bias", "other")}
    for tensor, gold in zip(rows, sorted(entries, key=lambda r: r["data_offset"]), strict=True):
        a, n = tensor["offset"], tensor["bytes"]
        need(
            (tensor["name"], a, n, tensor["shape"], tensor["type"])
            == (
                gold["name"],
                gold["data_offset"],
                gold["n_bytes"],
                gold["shape"],
                dtype[gold["tensor_type"]],
            ),
            "descriptor differs from C283: " + gold["name"],
        )
        overlap = sum(max(0, min(a + n, end) - max(a, start)) for start, end in ranges)
        need(overlap in (0, n), "partially classified tensor: " + gold["name"])
        role = EXPERT.fullmatch(tensor["name"])
        kind = role[1] if role else "other"
        if overlap:
            counts[kind]["tensors"] += 1
            counts[kind]["bytes"] += n
    spans = sum(b - a for a, b in ranges)
    total = sum(t["bytes"] for t in rows)
    need(
        sum(c["bytes"] for c in counts.values()) == native["deferred_bytes"] == spans,
        "uncounted range",
    )
    need(native["total_bytes"] == total == native["dense_bytes"] + spans, "byte conservation")
    return counts


def run(args, out):
    ik, build = args.source.resolve(), args.build.resolve()
    WORKER["require_clean"](ik)
    WORKER["require_clean"](HERE)
    need(WORKER["revision"](ik) == [WORKER["PIN"], WORKER["TREE"]], "fork pin")
    ggml, llama = build / "ggml/src/libggml.so", build / "src/libllama.so"
    need((sha(ggml), sha(llama)) == (LIBGGML, LIBLLAMA), "R03 identity")
    raw_inventory = args.inventory.read_bytes()
    need(hashlib.sha256(raw_inventory).hexdigest() == WORKER["INVENTORY"], "C283 identity")
    WORKER["layer_geometry"](raw_inventory)
    with args.model.open("rb", buffering=0) as f:
        before = os.fstat(f.fileno())
        header = f.read(LEGACY["HEADER_SIZE"])
        after = os.fstat(f.fileno())
    need(
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        == (after.st_dev, after.st_ino, LEGACY["MODEL_SIZE"], after.st_mtime_ns, after.st_ctime_ns)
        and hashlib.sha256(header).hexdigest() == LEGACY["HEADER_SHA"],
        "original GGUF header identity",
    )
    binary = out / "index"
    paths = [ik / p for p in ("include", "src", "ggml/include", "ggml/src", "vendor")]
    cmd = [
        "/usr/bin/c++",
        "-O1",
        "-std=c++17",
        *("-I" + str(p) for p in paths),
        HERE / "index.cpp",
        llama,
        ggml,
        "-Wl,-rpath," + str(llama.parent) + ":" + str(ggml.parent),
        "-o",
        binary,
    ]
    with (out / "build.log").open("xb") as log:
        subprocess.run(cmd, env=env, check=True, timeout=90, stdout=log, stderr=log)
    closure = WORKER["output"](["ldd", "-r", binary])
    for p in (ggml, llama):
        need(str(p) in closure and "undefined symbol:" not in closure, "unsealed ELF closure")
    off, blocks = child(binary, header, before.st_size, "off", out)
    on, _ = child(binary, header, before.st_size, "on", out)
    short, _ = child(binary, header, before.st_size - 1, "short", out)
    need(short["status"] == "REJECTED_SHORT_TENSOR_RANGE", "short file control")
    need(off.pop("defer") is False and on.pop("defer") is True and off == on, "index control")
    counts = compare(on, [json.loads(line) for line in raw_inventory.splitlines()[1:]])
    classification = (
        "PASS_DEFER_INDEX"
        if counts["weight"]["tensors"] == 108 and not counts["other"]["tensors"]
        else "NO_GO_INDEX_COVERAGE"
    )
    return dict(
        status=classification,
        code_revision=WORKER["revision"](HERE),
        pin=WORKER["PIN"],
        header_sha256=LEGACY["HEADER_SHA"],
        header_logical_bytes=len(header),
        view_allocated_bytes=blocks,
        inventory_sha256=WORKER["INVENTORY"],
        tensor_count=len(on["tensors"]),
        indexed=counts,
        dense_bytes=on["dense_bytes"],
        deferred_bytes=on["deferred_bytes"],
        ranges=len(on["ranges"]),
        short=short["status"],
        native_sha256=sha(binary),
        libllama_sha256=LIBLLAMA,
        libggml_sha256=LIBGGML,
        native_off_sha256=sha(out / "off.stdout"),
        native_on_sha256=sha(out / "on.stdout"),
        original_weight_bytes_supplied=0,
        forwards=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "build", "model", "inventory", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700, exist_ok=False)
    try:
        receipt = run(args, out)
    except Exception as exc:
        (out / "FAIL.json").write_text(json.dumps({"error": str(exc), "status": "FAIL"}) + "\n")
        raise
    with (out / "receipt.json").open("x") as sink:
        json.dump(receipt, sink, indent=2, sort_keys=True)
        sink.write("\n")
    print(receipt["status"], sha(out / "receipt.json"))
