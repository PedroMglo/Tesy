"""Build the qualified C269 fusion without its numerical counter, with the original client."""

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = Path("research/qualification-retake/parked_fusion/timing")
NUM_BUILDER = "e4d226d6c5e1d32c1bf13f65cb57f630da46dea6f2286e0e6c1abdb33e88f606"
NUM_RECEIPT = "c7926f18eb558240f3d14a2be2ed12872de98b2fbfbf5ed6b57b51d9140960bc"
REAL_RECEIPT = "7b7f543d76d4c3a7f13200fa962a07d8ab31595ea821392f7c6982362b8a3b54"
COUNTED_SOURCE = "625c6403291442daad1d3827e303488084df871e87081fa626bca9d82ab27d50"
COUNTED_CPU = "526a4684edd7eb0e60fb16dabb99d23198f9ede8822ef716c480b5e853c3a208"
DEFINITION = b"""\
// Numerical fixture witness: one increment per region, by the graph executor
// with ith == 0. There is no mutation of the routing, graph or shared ID data.
static _Atomic uint64_t tesy_parked_regions = 0;
GGML_BACKEND_API uint64_t tesy_parked_fusion_count(void);
uint64_t tesy_parked_fusion_count(void) {
    return atomic_load_explicit(&tesy_parked_regions, memory_order_relaxed);
}

"""
INCREMENT = b"    if (params->ith==0) atomic_fetch_add_explicit(&tesy_parked_regions, 1, memory_order_relaxed);\n"  # noqa: E501
TIMING_SOURCE = "e70b89face0637f0446549fab03ae59ef103707edddcc14f6f8f6df3ed98ad88"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def uncount(original):
    require(digest(original) == COUNTED_SOURCE, "numerical translation unit mismatch")
    d = original.find(DEFINITION)
    i = original.find(INCREMENT)
    require(
        original.count(DEFINITION) == original.count(INCREMENT) == 1 and d >= 0 and i > d,
        "counter spans",
    )
    # Exact unchanged byte ranges. Reinsert both spans to independently prove
    # reconstruction of the authenticated source, including all graph guards.
    bare = original[:d] + original[d + len(DEFINITION) : i] + original[i + len(INCREMENT) :]
    split = i - len(DEFINITION)
    require(
        bare[:d] + DEFINITION + bare[d:split] + INCREMENT + bare[split:] == original
        and digest(bare) == TIMING_SOURCE
        and b"tesy_parked_fusion_count" not in bare
        and b"tesy_parked_regions" not in bare,
        "candidate differs beyond the counter",
    )
    return bare


def build(a, r):
    path = HERE.parent / "numerical/build.py"
    require(digest(path.read_bytes()) == NUM_BUILDER, "numerical builder identity")
    spec = importlib.util.spec_from_file_location("qualified_fusion_build", path)
    num = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(num)
    mm, scope = num.old_modules()
    c = scope.cgroup()
    scope.validate_events(c)
    project, backend = a.repo.resolve(), a.backend.resolve()
    out, old = a.new_output_dir.resolve(), a.numerical_build.resolve()
    require(HERE == project / STUDY and not mm.git(project, "status", "--porcelain"), "checkout")
    require(
        mm.git(backend, "rev-parse", "HEAD") == mm.PIN
        and not mm.git(backend, "status", "--porcelain", "--", "ggml"),
        "C269 pin",
    )
    counted = scope.checked(old / "receipt.json", NUM_RECEIPT)
    real = scope.checked(a.real_receipt, REAL_RECEIPT)
    require(
        counted["decision"] == "GO_REAL_TILE"
        and real["decision"] == "GO_TIMING_FIXTURE"
        and real["numerical_receipt_sha256"] == NUM_RECEIPT
        and counted["candidate_cpu_sha256"] == real["candidate_cpu_sha256"] == COUNTED_CPU
        and counted["source_fusion_sha256"] == COUNTED_SOURCE,
        "exactness gates",
    )
    num_src = old / "candidate" / mm.SOURCE.name
    num_elf = old / "candidate" / mm.CPU
    require(mm.sha(num_elf) == COUNTED_CPU, "counted DSO")
    prior_client = a.suffix_build.resolve()
    scope.checked(prior_client / "receipt.json", mm.HARNESS_RECEIPT)
    require(mm.sha(prior_client / "suffix-layer") == mm.HARNESS, "original uninstrumented client")
    r.update(
        commit=mm.git(project, "rev-parse", "HEAD"),
        tree=mm.git(project, "rev-parse", "HEAD^{tree}"),
        c269_commit=mm.PIN,
        numeric_build_sha256=NUM_RECEIPT,
        real_receipt_sha256=REAL_RECEIPT,
        suffix_build_receipt_sha256=mm.HARNESS_RECEIPT,
        source_sha256={n: mm.sha(HERE / n) for n in ("build.py", "protocol.md")},
        dependencies=counted["dependencies"] | {"numeric_builder": NUM_BUILDER},
        counted_source_sha256=COUNTED_SOURCE,
        counted_cpu_sha256=COUNTED_CPU,
        original_cpu_sha256=mm.CPU_SHA,
        base_sha256=mm.BASE_SHA,
    )
    b = backend / "build-c269-cuda"
    libs = b / "bin"
    for base, pins in (
        (Path("/"), mm.TOOLS),
        (b, mm.CMAKE),
        (libs, {mm.BASE: mm.BASE_SHA, mm.CPU: mm.CPU_SHA}),
    ):
        require(
            all(mm.sha(base / name) == h for name, h in pins.items()), "toolchain and original DSOs"
        )
    raw = mm.text(["/usr/bin/ninja", "-C", b, "-t", "commands", mm.TARGET]).splitlines()[-1]
    inputs = {s: mm.sha(b / s) for s in shlex.split(raw) if s.endswith(".o") or s in mm.DEPS}
    require(mm.sha_text(raw) == mm.LINK_SHA and mm.manifest(inputs) == mm.INPUTS_SHA, "link inputs")
    candidate = out / "candidate"
    candidate.mkdir()
    src, obj = candidate / mm.SOURCE.name, candidate / (mm.SOURCE.name + ".o")
    original = num_src.read_bytes()
    bare = uncount(original)
    with src.open("xb") as stream:
        stream.write(bare)
    require(src.read_bytes() == bare, "generated source write")
    r.update(
        timing_source_sha256=TIMING_SOURCE,
        counter_only_delta=True,
        deleted_spans_bytes=[len(DEFINITION), len(INCREMENT)],
        link_inputs_sha256=mm.INPUTS_SHA,
        cmake=mm.CMAKE,
        tools=mm.TOOLS,
    )

    # Reuse the exact argv which built the counted reference and relink only
    # the candidate object. Recorded paths may have moved with the raw archive.
    prev = list(counted["commands"]["compile"])
    require(
        prev[0] == "/usr/bin/env" and prev[1].startswith("--chdir="), "numeric compile envelope"
    )
    cc = prev[2:]
    obj_pos = cc.index("-o") + 1
    src_pos = cc.index("-c") + 1
    require(
        Path(cc[obj_pos]).name == obj.name and Path(cc[src_pos]).name == src.name, "TU arguments"
    )
    mm.replace(cc, cc[obj_pos], obj)
    mm.replace(cc, cc[src_pos], src)
    (oldmap,) = [s for s in cc if s.startswith("-fmacro-prefix-map=")]
    origin = Path(oldmap.split("=", 2)[2])
    require(origin.samefile((backend / mm.SOURCE).parent), "compiler path remap")
    mm.replace(cc, oldmap, f"-fmacro-prefix-map={candidate}={origin}")
    scope.run(["/usr/bin/env", f"--chdir={b}", *cc], mm.ENV, out / "compile", c, r)
    scope.run(
        ["/usr/bin/env", f"--chdir={b}", *mm.linker(raw, candidate, obj)],
        mm.ENV,
        out / "link",
        c,
        r,
    )
    require(all(mm.sha(b / s) == h for s, h in inputs.items()), "original object modified")
    (candidate / "libggml-cpu.so.0").symlink_to(mm.CPU)
    exe = out / "suffix-layer"
    shutil.copy2(prior_client / "suffix-layer", exe)
    require(mm.sha(exe) == mm.HARNESS, "harness copy")
    providers = {}
    for role, directory in (("original", libs), ("candidate", candidate)):
        env = mm.ENV | {"LD_LIBRARY_PATH": os.pathsep.join(map(str, (directory, libs)))}
        providers[role] = mm.loader(
            exe, env, {"libggml-cpu.so.0": directory / mm.CPU, "libggml-base.so.0": libs / mm.BASE}
        )
    elf = candidate / mm.CPU
    getter = "tesy_parked_fusion_count"
    variable = "tesy_parked_regions"
    require(
        getter in mm.text(["/usr/bin/nm", "-D", "--defined-only", num_elf]),
        "counted reference lacks getter",
    )
    require(
        variable in mm.text(["/usr/bin/nm", "--defined-only", num_elf]),
        "counted reference lacks counter",
    )
    for binary in (obj, elf, exe):
        syms = mm.text(["/usr/bin/nm", "--defined-only", binary])
        require(getter not in syms and variable not in syms, "remaining counter symbol")
    require(getter not in mm.text(["/usr/bin/nm", "-D", elf]), "counter import/export")
    require(getter.encode() not in exe.read_bytes(), "unexpected counter-observing client")
    outsha = mm.sha(elf)
    require(
        outsha not in (COUNTED_CPU, mm.CPU_SHA) and mm.sha(src) == TIMING_SOURCE, "unique image"
    )
    r.update(
        status="PASS_C269_UNCOUNTED_FUSION_BUILD",
        counter_symbols_absent=True,
        providers=providers,
        candidate_cpu_sha256=outsha,
        binary_sha256=mm.HARNESS,
        memory_events=scope.validate_events(c),
        peak_bytes=int((c / "memory.peak").read_text()),
        swap_peak_bytes=int((c / "memory.swap.peak").read_text()),
        model_weight_bytes=0,
        graph_computations=0,
        gpu_compute=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "repo",
        "backend",
        "numerical-build",
        "real-receipt",
        "suffix-build",
        "new-output-dir",
    ):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    r = {"status": "FAIL_PRESERVED", "commands": {}}
    try:
        build(a, r)
    except Exception as exc:
        r.update(
            error_type=type(exc).__name__,
            reason=str(exc) if isinstance(exc, ValueError) else "see private build logs",
        )
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, indent=2, allow_nan=False) + "\n")
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
