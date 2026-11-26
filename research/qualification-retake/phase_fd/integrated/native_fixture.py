"""Exercise the instrumented C269 manager object through the real CPU remap scheduler."""

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = "e5042bfb23527a1763b28ca2098c0a00700383d07ff403a97d52da4bcdf422a6"
PROTOCOL = "7914cad4f30fec2fb29c0af564507d0da872ba113d20ae1ccb9addacbda2f85b"
RECORD = struct.Struct("<QQQqqq12i")
NAMES = (
    "ns begin gen a b c kind call tile wave layer expert slot worker component fd error reserved"
).split()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned(path, expected):
    need(path.is_file() and sha(path) == expected, "digest " + path.name)
    return path


def read_manifest(path, expected):
    # build.py emits pretty JSON but seals the sorted, compact representation.
    record = json.loads(path.read_bytes())
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    need(len(record) == 171 and hashlib.sha256(encoded).hexdigest() == expected, "build manifest")
    return record


def bounds():
    cg_path = Path("/proc/self/cgroup").read_text().strip()
    need(cg_path.startswith("0::/") and "tesy-phase-fd" in cg_path, "dedicated cgroup")
    cg = Path("/sys/fs/cgroup") / cg_path[3:].lstrip("/")
    need(int((cg / "memory.max").read_text()) == 512 << 20, "cgroup memory")
    need(int((cg / "memory.swap.max").read_text()) == 0, "swap")
    return cg


def borrowed(source):
    # Copy the exact measured statements. The stand-ins supply only the outer call/graph handles.
    a = source.index("    if (pfj::journal)", source.index("int32_t llama_decode("))
    b = source.index("    if (ret != 0", a)
    call = source[a:b]
    a = source.index(
        "    if (pfj::journal)", source.index("// set the input data for the input tensors")
    )
    b = source.index("    if (status != GGML_STATUS_SUCCESS)", a)
    graph = source[a:b]
    need(call.count("ctx->decode(batch)") == 1 and call.count("pfj::returned") == 1, "call seam")
    need(
        graph.count("graph_compute(res->get_gf(),") == 1 and graph.count("pfj::graph_return") == 1,
        "graph seam",
    )
    return (
        "int borrowed_call(ContextLike *ctx, TestBatch batch) {\n"
        + call
        + "return ret;\n}\n"
        + "template<class F> auto borrowed_graph(ModelLike model, TestBatch ubatch,\n"
        + "F graph_compute) {\n"
        + "struct { int get_gf() const {return 0;} } stub; const auto *res=&stub;\n"
        + graph
        + "return status;\n}\n"
    )


def inspect(path, native, inherited, fail):
    data = path.read_bytes()
    magic, version, size, cap, tried, kept, flags, reserved = struct.unpack_from("<8s7Q", data)
    need(
        (magic, version, size, cap, flags, reserved) == (b"TESYPF1\0", 1, 96, 262144, 1, 0),
        "sealed nonoverflowing journal",
    )
    need(tried == kept and len(data) == 64 + 96 * kept, "journal coverage")
    events = [dict(zip(NAMES, vals, strict=True)) for vals in RECORD.iter_unpack(data[64:])]
    kinds = Counter(e["kind"] for e in events)
    need(kinds[5] == 1440 and kinds[7] == 1 and kinds[8] == 108, "entry state and geometry")
    need(
        kinds[24] == 4
        and {e["worker"] for e in events if e["kind"] == 24} == set(range(4))
        and kinds[25] == 1
        and events[-1]["kind"] == 25,
        "four workers",
    )
    need(events[-1]["a"] == events[-1]["b"] == 0 and events[-1]["c"] == int(fail), "terminal state")
    enters = [e for e in events if e["kind"] == 1]
    triples = [(e["a"], e["b"], e["c"]) for e in enters]
    expected = [(1, 32, 32)] if inherited else [(32, 0, 31), (1, 32, 32)]
    need(
        triples == expected and [e["call"] for e in enters] == list(range(1, len(expected) + 1)),
        "call lineage",
    )
    need([(e["a"], e["b"], e["c"]) for e in events if e["kind"] == 3] == expected, "tile lineage")
    need(kinds[2] == kinds[4] == len(enters) and kinds[9] == kinds[23] == len(enters), "returns")
    need(kinds[19] == kinds[20] == len(enters), "consumer barriers")
    need(kinds[27] == (1 if inherited else 33), "rank rows")
    reads = [e for e in events if e["kind"] == 15]
    for er in reads:
        need(
            0 <= er["worker"] < 4
            and 0 <= er["component"] < 3
            and er["fd"] >= 0
            and er["ns"] >= er["begin"],
            "read identity",
        )
        if er["call"] > 0:
            need(er["begin"] > 0 and er["tile"] == 1 and er["layer"] in (0, 1), "read origin")
    late = [e for e in reads if e["layer"] == 0 and e["expert"] == 127 and e["component"] == 2]
    need(len(late) == 1 and late[0]["call"] == (0 if inherited else 1), "earlier generation")
    read = late[0]
    need(read["b"] == 8192 and read["c"] == 4192 - int(fail), "sufficient or one byte short")
    need((read["begin"] == 0) == inherited, "inherited read start")
    returns = [e for e in events if e["kind"] == 2]
    need(read["ns"] >= returns[-1]["ns"], "read completed after external returns")
    pending = [e for e in events if e["kind"] == 26 and e["expert"] == 127]
    need(
        [e["call"] for e in pending] == list(range(1, len(enters) + 1))
        and all(e["gen"] == read["gen"] and e["a"] == e["b"] == 1 for e in pending),
        "pending at cuts",
    )
    if inherited:
        need(
            any(e["kind"] == 5 and e["expert"] == 127 and e["a"] == e["b"] == 1 for e in events),
            "inherited in entry",
        )
    else:
        need(
            len(reads) == native["reads"]
            and sum(e["b"] for e in reads) == native["requested"]
            and sum(e["c"] for e in reads) == native["returned"],
            "independent syscall ledger",
        )
        need(
            sum(e["a"] for e in events if e["kind"] == 16) == native["payload"]
            and kinds[17] == native["publications"]
            and kinds[18] == int(fail),
            "payload and publication",
        )
        need(kinds[11] == kinds[12] == kinds[13] == 40, "reservation to claim")
    return dict(
        events=len(events),
        calls=len(enters),
        reads=len(reads),
        journal_sha256=sha(path),
        inherited_generation=inherited,
        tail_returned=read["c"],
        sealed=True,
    )


def run(a, result):
    start = time.monotonic()
    cg = bounds()
    initial = (cg / "memory.events").read_text()
    out = a.new_output_dir.resolve()
    rev = subprocess.check_output(["git", "-C", HERE, "rev-parse", "HEAD"], text=True).strip()
    need(
        rev == a.expect_head
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "frozen checkout",
    )
    build = a.build_dir.resolve()
    rec = json.loads(pinned(build / "receipt.json", BUILD).read_bytes())
    need(rec["status"] == "PASS_C269_PHASE_FD_PRIVATE_BUILD", "build")
    pinned(HERE / "native-fixture.md", PROTOCOL)
    backend = a.backend.resolve()
    compiled = backend / "build-c269-cuda"
    inputs = read_manifest(build / "inputs.json", rec["inputs_sha256"])
    overlay = build / "overlay/src"
    for name, digest in rec["overlay_sha256"].items():
        pinned(build / "overlay" / name, digest)
    manager = pinned(
        build / "candidate/llama-moe-stream.cpp.o",
        rec["phases"]["candidate"]["objects"]["src/llama-moe-stream.cpp"],
    )
    support = [
        pinned(compiled / name, inputs[name])
        for name in (
            "src/CMakeFiles/llama.dir/llama-mmap.cpp.o",
            "src/CMakeFiles/llama.dir/llama-impl.cpp.o",
            "bin/libggml-cpu.so.0.15.3",
            "bin/libggml-base.so.0.15.3",
        )
    ]
    markers = out / "borrowed-context.inc"
    markers.write_text(borrowed((overlay / "llama-context.cpp").read_text()))
    exe = out / "phasefd-cpu"
    libs = compiled / "bin"
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        TMPDIR=str(out),
        LD_LIBRARY_PATH=str(libs),
        OMP_NUM_THREADS="4",
        CUDA_VISIBLE_DEVICES="",
        TESY_CPU_WAVE_SKIP_PARKED="1",
    )

    def cmd(argv, label, extra):
        with (
            (out / (label + ".stderr")).open("xb") as err,
            (out / (label + ".stdout")).open("xb") as stdout,
        ):
            p = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=err,
                env={**env, **extra},
                timeout=max(0.01, 115 - time.monotonic() + start),
                check=False,
            )
        need(p.returncode == 0, label + " exit " + str(p.returncode))

    compiler = Path("/usr/bin/g++-15")
    pinned(compiler, rec["compiler_sha256"])
    args = [
        compiler,
        "-std=c++17",
        "-O1",
        "-fPIC",
        "-g0",
        "-pthread",
        "-I" + str(overlay),
        "-I" + str(out),
    ]
    args.extend("-I" + str(backend / name) for name in ("src", "include", "ggml/include"))
    cmd(
        [*args, HERE / "native-fixture.cpp", manager, *support, "-Wl,--wrap=pread", "-o", exe],
        "compile",
        {},
    )
    result.update(
        build_sha256=BUILD,
        candidate_sha256=rec["candidate_sha256"],
        program_sha256=sha(Path(__file__)),
        source_sha256=sha(HERE / "native-fixture.cpp"),
        source_commit=rev,
        protocol_sha256=PROTOCOL,
        markers_sha256=sha(markers),
        context_proof="pinned_source_markers_in_fixture",
        manager_object_sha256=sha(manager),
        executable_sha256=sha(exe),
        arms={},
    )
    for key in ("off-ok", "on-ok", "off-short", "on-short", "on-inherited"):
        result["stage"] = key
        mode, test = key.split("-")
        inherited = test == "inherited"
        fail = test == "short"
        arm = out / key
        arm.mkdir()
        file = arm / "journal.pfj"
        extra = {"TESY_PHASE_FD_FILE": str(file)} if mode == "on" else {}
        if inherited:
            extra["TESY_PHASE_FD_TRIGGER"] = str(arm / "trigger")
        cmd([exe, arm, "short" if fail else "ok", "inherited" if inherited else "both"], key, extra)
        native = json.loads((out / (key + ".stdout")).read_bytes())
        need(native["status"] == "PASS" and native["joined"] == 4, "native validation")
        result["arms"][key] = dict(
            native=native, observer=inspect(file, native, inherited, fail) if mode == "on" else None
        )
        need(file.exists() == (mode == "on"), "OFF journal")
    for t in ("ok", "short"):
        need(
            result["arms"]["off-" + t]["native"] == result["arms"]["on-" + t]["native"],
            "OFF/ON syscall differences",
        )
    need(
        (cg / "memory.events").read_text() == initial
        and int((cg / "memory.swap.current").read_text()) == 0,
        "resource events",
    )
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    need(size < (64 << 20) - 65536, "output cap")
    result.update(
        status="PASS_C269_PHASE_FD_MANAGER_AND_BOUNDARIES",
        stage="done",
        output_bytes_before_receipt=size,
        peak_bytes=int((cg / "memory.peak").read_text()),
        elapsed_s=round(time.monotonic() - start, 3),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "build-dir", "new-output-dir"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--expect-head", required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = {"status": "FAIL_PRESERVED", "stage": "preflight"}
    try:
        run(a, result)
        rc = 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyError,
        struct.error,
    ) as exc:
        result["error"] = str(exc)
        rc = 1
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
