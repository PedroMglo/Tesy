"""Serve the first gate/up rows of a real rank before the remaining C291 pages arrive."""

import argparse
import ctypes as ct
import mmap
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RANK = run_path(HERE / "run.py")
A, need, sha, save = (RANK[k] for k in ("A", "need", "sha", "save"))
N, STRIDE, Vec, Ptr, bind = (A[k] for k in ("N", "STRIDE", "Vec", "Ptr", "bind"))
PAGE = 4096
ROWS = 32
ROLES = ("gate", "up")


def extent(offset, count):
    return (offset // PAGE * PAGE, (offset + count + PAGE - 1) // PAGE * PAGE)


def identity(fd):
    st = os.fstat(fd)
    return dict(
        dev=st.st_dev,
        inode=st.st_ino,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def arm(fd, base, components, chunks, first, qb, ref, dot):
    total = max(e for _, e in chunks)
    by_offset = sorted(chunks)
    need(
        by_offset[0][0] == 0
        and all(x[1] == y[0] for x, y in zip(by_offset[:-1], by_offset[1:], strict=True))
        and all(0 <= b < e <= total and b % PAGE == e % PAGE == 0 for b, e in chunks),
        "disjoint full-page cover",
    )
    results = {}
    with mmap.mmap(-1, total) as buffer:
        for i, (begin, end) in enumerate(chunks, 1):
            with memoryview(buffer)[begin:end] as part:
                need(os.preadv(fd, [part], base + begin) == end - begin, "direct read length")
            if i == first:
                for k in ROLES:
                    offset = components[k]["packed_relative_offset"]
                    need(
                        any(b <= offset and offset + ROWS * STRIDE <= e for b, e in chunks[:i]),
                        "completed rows before compute",
                    )
                    result = (ct.c_float * ROWS)()
                    for j in range(ROWS):
                        word = ct.c_ubyte.from_buffer(buffer, offset + j * STRIDE)
                        dot(N, ct.byref(result, j * 4), 0, ct.byref(word), 0, qb, 0, 1)
                        del word
                    need(bytes(result) == bytes(ref[k])[: 4 * ROWS], "native captured rows " + k)
                    results[k] = sha(bytes(result))
        for k, c in components.items():
            offset = c["packed_relative_offset"]
            with memoryview(buffer)[offset : offset + c["size_bytes"]] as payload:
                need(sha(payload) == c["sha256"], "complete " + k)
    return dict(
        completions_before_compute=first,
        bytes_before_compute=sum(e - b for b, e in chunks[:first]),
        total_requested_bytes=total,
        spans=[list(span) for span in chunks],
        output_sha256=results,
    )


def measure(a):
    read = A["receipt"]
    checked = A["file_sha"]
    need(
        checked(HERE / "result.json")
        == "35d6cb4e37fc49c903d66654f9578ed98a9365484026e678a1ca0d453a9c661d",
        "routed projection receipt",
    )
    proof = read(HERE / "result.json")
    need(checked(a.derived / "receipt.json") == A["OLD"]["C291"], "pack constructor")
    pack = read(a.derived / "receipt.json")
    index = a.derived / "integral-index.json"
    need(checked(index) == pack["index_sha256"], "layout")
    (entry,) = [e for e in read(index)["experts"] if (e["layer"], e["expert"]) == (0, 28)]
    components = {
        k: next(c for c in entry["components"] if c["name"] == f"blk.0.ffn_{k}_exps.weight")
        for k in (*ROLES, "down")
    }
    need(
        all(
            c["sha256"] == proof["stages"][k]["weight_sha256"] and c["size_bytes"] == N * STRIDE
            for k, c in components.items()
        ),
        "three true slabs",
    )
    offsets = [components[k]["packed_relative_offset"] for k in ("gate", "down", "up")]
    need(
        offsets == [i * N * STRIDE for i in range(3)] and entry["pack_offset"] % PAGE == 0,
        "C291 geometry",
    )
    _, total = extent(0, 3 * N * STRIDE)
    gate, up = [extent(components[k]["packed_relative_offset"], ROWS * STRIDE) for k in ROLES]
    parts = [gate, up, (gate[1], up[0]), (up[1], total)]
    need(2 * total < 30 * 2**20, "NVMe request budget")
    lib = read(HERE.parent / "activation/result.json")
    need(
        checked(a.base) == lib["base_sha256"] and checked(a.cpu) == lib["original_cpu_sha256"],
        "registered CPU",
    )
    base = ct.CDLL(str(a.base), mode=ct.RTLD_GLOBAL)
    cpu = ct.CDLL(str(a.cpu))
    bind(cpu, "ggml_cpu_init", [])()
    traits = bind(cpu, "ggml_get_type_traits_cpu", [ct.c_int], ct.POINTER(A["Traits"]))
    quant = bind(cpu, "quantize_row_q8_0", [Ptr, Ptr, ct.c_int64])
    dot = bind(
        cpu,
        "ggml_vec_dot_mxfp4_q8_0",
        [ct.c_int, Ptr, ct.c_size_t, Ptr, ct.c_size_t, Ptr, ct.c_size_t, ct.c_int],
    )
    need(
        base
        and traits(39).contents.vec_dot == ct.cast(dot, Ptr).value
        and traits(39).contents.vec_dot_type == 8
        and traits(8).contents.from_float == ct.cast(quant, Ptr).value,
        "type registration",
    )
    src, ref, _ = RANK["capture"](a.archive)
    qb = A["Bits"]()
    quant(Vec.from_buffer_copy(src["gate"]), qb, N)
    need(
        src["gate"] == src["up"] and sha(bytes(qb)) == proof["stages"]["gate"]["q8_sha256"],
        "target activation",
    )
    results = {}
    fd = os.open(pack["pack_path"], os.O_RDONLY | os.O_DIRECT | os.O_CLOEXEC)
    try:
        need(identity(fd) == pack["pack_stat"], "internal pack before direct reads")
        for role in ("complete", "partial") if a.order == "CP" else ("partial", "complete"):
            chunks, first = ([(0, total)], 1) if role == "complete" else (parts, 2)
            results[role] = arm(fd, entry["pack_offset"], components, chunks, first, qb, ref, dot)
        need(identity(fd) == pack["pack_stat"], "internal pack after direct reads")
    finally:
        os.close(fd)
    need(
        results["complete"]["output_sha256"] == results["partial"]["output_sha256"]
        and results["complete"]["total_requested_bytes"]
        == results["partial"]["total_requested_bytes"]
        and results["partial"]["bytes_before_compute"] < total,
        "first partial consumption",
    )
    return dict(
        status="MEASURED_EXACT_PARTIAL_CPU_CONSUMPTION",
        decision="GO_CONCURRENCY_FIXTURE_ONLY",
        arms=results,
        rows_per_projection=ROWS,
        logical_gguf_payload_bytes=3 * N * STRIDE,
        page_bytes=PAGE,
        model_sha256=proof["model_sha256"],
        pack_sha256=pack["pack_sha256"],
        index_sha256=pack["index_sha256"],
        expert=28,
        position=189,
        layer=0,
        slot=3,
        generation=6,
        program_sha256=checked(HERE / "stripe.py"),
        protocol_sha256=checked(HERE / "stripe-protocol.md"),
        model_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("derived", "archive", "base", "cpu", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--order", choices=("CP", "PC"), required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    start = time.monotonic()
    try:
        cg = A["scope"]()
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
        need(
            not subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE), "clean source"
        )
        save(
            a.new_output_dir / "provenance.json",
            dict(
                commit=head,
                protocol_sha256=A["file_sha"](HERE / "stripe-protocol.md"),
                scope=cg.name,
                order=a.order,
            ),
        )
        r = measure(a)
        events = dict(s.split() for s in (cg / "memory.events").read_text().splitlines())
        need(
            (cg / "memory.swap.current").read_text().strip() == "0"
            and int(events["oom"]) == int(events["oom_kill"]) == 0
            and time.monotonic() - start < 60,
            "scope budget",
        )
        save(
            a.new_output_dir / "resources.json",
            dict(
                elapsed_s=time.monotonic() - start,
                peak_bytes=int((cg / "memory.peak").read_text()),
                swap_bytes=0,
            ),
        )
        save(a.new_output_dir / "decision.json", r)
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    print(r["decision"])
