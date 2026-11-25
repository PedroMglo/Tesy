"""Build and verify the numerical parked fusion in four fresh CPU processes."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = Path("research/qualification-retake/parked_fusion/numerical")
MMID_RECEIPT = "6da2f9ff2695e9b80b34ce4c8ceff0796ba7541ad219541b7f9ac82936f6a05c"
TOPOLOGY = "abbe8e59d3318aa2691c93e3260cfd41ee9fedbe0ef91fce0bdc0112ee144238"
OLD_BUILDER = "5a06401d0c42a911870dfc3a9ef26031ed7f78e717423b1afd9aac754727cc31"
OLD_KERNEL = "238ade7c7dd439700fe63e2c07efa30b563e5b0c5022cb055c5d34c9687cbc8f"
MODES = ("original", "off", "mmid", "fusion")


def need(value, why):
    if not value:
        raise ValueError(why)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def module(name, path, pin=None):
    need(not pin or sha(path) == pin, "source identity " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def old_modules():
    old = HERE.parents[1] / "parked_mmid"
    # The earlier standalone builder imports its own kernel by that basename.
    # Avoid binding it to this study's different kernel.py when loaded as a module.
    original = sys.modules.get("kernel")
    try:
        sys.modules["kernel"] = module("parked_mmid_kernel", old / "kernel.py", OLD_KERNEL)
        mm = module("parked_mmid_build", old / "build.py", OLD_BUILDER)
    finally:
        if original is None:
            sys.modules.pop("kernel", None)
        else:
            sys.modules["kernel"] = original
    scope = module("parked_fusion_scope", HERE.parent / "topology.py", TOPOLOGY)
    return mm, scope


def checked_parts(row, data, mode):
    need(
        mode in MODES
        and row["mode"] == mode
        and row["status"] == "PASS_NUMERIC_PARKED_FUSION_FIXTURE",
        "numeric fixture identity",
    )
    need(
        sys.byteorder == "little"
        and len(data) == row["total_bytes"]
        and type(row["total_bytes"]) is int
        and 0 < len(data),
        "output encoding or size",
    )
    cases = row["cases"]
    ids = [c["id"] for c in cases]
    need(all(isinstance(s, str) and s for s in ids) and len(set(ids)) == len(ids), "case identity")
    used = 0
    seen = 0
    parts = []
    for c in cases:
        n = c["bytes"]
        need(
            type(c["offset"]) is int
            and c["offset"] == used
            and type(n) is int
            and n > 0
            and n % 4 == 0
            and n <= len(data) - used,
            "case span",
        )
        view = memoryview(data)[used : used + n]
        expected, observed = c["expected_fusions"], c["observed_fusions"]
        need(
            type(expected) is int and expected >= 0 and type(observed) is int and observed >= 0,
            "fusion count type",
        )
        finite = next(
            (j for j, b in enumerate(view.cast("I")) if b & 0x7F800000 == 0x7F800000), None
        )
        parts.append(
            dict(
                id=c["id"],
                offset=used,
                bytes=n,
                expected_fusions=expected,
                observed_fusions=observed,
                first_nonfinite_index=finite,
                sha256=hashlib.sha256(view).hexdigest(),
            )
        )
        used += n
        seen += observed
    need(used == len(data) and seen == row["fused_regions"], "raw or counter conservation")
    return parts


def check_population(row, parts, mode):
    """Count the four observed tensors, optional fifth output, and inactive padding cells."""
    spec = []
    for tokens in (1, 2, 20, 32):
        for threads in (1, 8):
            prefix = f"n{tokens}-t{threads}-"
            area = tokens * 4 * 32
            for index, pattern in enumerate(
                ("parked", "last_active", "mixed", "one_parked", "active", "parked")
            ):
                spec.append(
                    (
                        f"{prefix}plain-{index}-{pattern}",
                        4 * 4 * area,
                        int(mode == "fusion" and tokens > 1 and pattern == "parked"),
                    )
                )
            for layout in (
                "strided",
                "requested",
                "consumer",
                "interleaved",
                "id_gap",
                "activation_alias",
            ):
                outputs = 5 if layout in ("requested", "consumer", "interleaved") else 4
                padding = 16 + 17 * tokens if layout == "strided" else 0
                spec.append(
                    (
                        f"{prefix}{layout}-0-parked",
                        4 * (outputs * area + padding),
                        int(mode == "fusion" and tokens > 1 and layout == "strided"),
                    )
                )
    need(
        len(spec) == len(parts) == 96
        and [(c["id"], c["bytes"], c["expected_fusions"]) for c in parts] == spec
        and sum(n for _, _, n in spec) == (18 if mode == "fusion" else 0)
        and row["total_bytes"] == sum(n for _, n, _ in spec),
        "prospective graph, padding, or branch population",
    )


def compare_cases(parts, data, original, gold, mode):
    need(
        [(x["id"], x["offset"], x["bytes"]) for x in parts]
        == [(x["id"], x["offset"], x["bytes"]) for x in original],
        "different fixture population",
    )
    for x, y in zip(parts, original, strict=True):
        failure = {"mode": mode, "case": x["id"]}
        if x["observed_fusions"] != x["expected_fusions"]:
            return failure | {
                "reason": "branch",
                "expected": x["expected_fusions"],
                "observed": x["observed_fusions"],
            }
        if x["first_nonfinite_index"] is not None:
            return failure | {"reason": "nonfinite", "f32_index": x["first_nonfinite_index"]}
        if x["sha256"] != y["sha256"]:
            start, n = x["offset"], x["bytes"]
            a = memoryview(data)[start : start + n].cast("I")
            b = memoryview(gold)[start : start + n].cast("I")
            j = next(k for k, (u, v) in enumerate(zip(a, b, strict=True)) if u != v)
            return failure | {
                "reason": "output_bits",
                "f32_index": j,
                "observed_bits": a[j],
                "reference_bits": b[j],
            }
    need(data == gold, "full bytes inconsistent with case hashes")
    return None


def build(a, r):
    mm, scope = old_modules()
    c = scope.cgroup()
    scope.validate_events(c)
    repo, backend = a.repo.resolve(), a.backend.resolve()
    out, old = a.new_output_dir, a.mmid_build.resolve()
    c55 = scope.checked(a.c55_receipt, scope.C55)
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and c55["canonical_memory"]["cap_max_bytes"] >= scope.CAP
        and not c55["concurrent"],
        "C55",
    )
    need(HERE == repo / STUDY and not mm.git(repo, "status", "--porcelain"), "measurement checkout")
    need(
        mm.git(backend, "rev-parse", "HEAD") == mm.PIN
        and not mm.git(backend, "status", "--porcelain", "--", "ggml", "vendor/nlohmann"),
        "C269",
    )
    ref = scope.checked(old / "receipt.json", MMID_RECEIPT)
    need(
        ref["status"] == "PASS_C269_PARKED_MMID_BUILD"
        and ref["reference_relink_identical"] is True,
        "unqualified reference",
    )
    r.update(
        commit=mm.git(repo, "rev-parse", "HEAD"),
        tree=mm.git(repo, "rev-parse", "HEAD^{tree}"),
        c269_commit=mm.PIN,
        c55_sha256=scope.C55,
        mmid_build_sha256=MMID_RECEIPT,
        source_sha256={
            n: sha(HERE / n) for n in ("build.py", "kernel.py", "fixture.cpp", "protocol.md")
        },
        dependencies={"mmid_builder": OLD_BUILDER, "mmid_kernel": OLD_KERNEL, "scope": TOPOLOGY},
    )
    b = backend / "build-c269-cuda"
    libs = b / "bin"
    for root, pins in (
        (Path("/"), mm.TOOLS),
        (b, mm.CMAKE),
        (libs, {mm.BASE: mm.BASE_SHA, mm.CPU: mm.CPU_SHA}),
    ):
        need(all(sha(root / n) == h for n, h in pins.items()), "historical tools/inputs")
    raw = mm.text(["/usr/bin/ninja", "-C", b, "-t", "commands", mm.TARGET]).splitlines()[-1]
    inputs = {s: sha(b / s) for s in shlex.split(raw) if s.endswith(".o") or s in mm.DEPS}
    need(
        mm.manifest(inputs) == mm.INPUTS_SHA and raw == ref["original_link_command"], "link inputs"
    )
    r.update(
        link_inputs_sha256=mm.INPUTS_SHA,
        tools=mm.TOOLS,
        cmake=mm.CMAKE,
        original_cpu_sha256=mm.CPU_SHA,
        base_sha256=mm.BASE_SHA,
    )
    prev = old / "candidate" / mm.SOURCE.name
    need(sha(prev) == ref["generated_source_sha256"], "qualified MMID translation unit")
    cand = out / "candidate"
    cand.mkdir()
    new = cand / mm.SOURCE.name
    obj = cand / (mm.SOURCE.name + ".o")
    kernel = module("qualified_numerical_kernel", HERE / "kernel.py")
    r["source_mmid_sha256"] = sha(prev)
    r["source_fusion_sha256"] = kernel.materialize(prev, new)
    need(sha(new) == r["source_fusion_sha256"], "source return")
    cc = list(ref["commands"]["compile"])
    mm.replace(cc, str(prev), new)
    mm.replace(cc, str(prev) + ".o", obj)
    (oldmap,) = [s for s in cc if s.startswith("-fmacro-prefix-map=")]
    origin = Path(str(oldmap).split("=", 2)[2])
    need(origin.samefile((backend / mm.SOURCE).parent), "historical source directory")
    mm.replace(cc, oldmap, f"-fmacro-prefix-map={cand}={origin}")
    env = mm.ENV
    scope.run(["/usr/bin/env", f"--chdir={b}", *cc], env, out / "compile", c, r)
    scope.run(["/usr/bin/env", f"--chdir={b}", *mm.linker(raw, cand, obj)], env, out / "link", c, r)
    need(all(sha(b / s) == digest for s, digest in inputs.items()), "mutated original object")
    (cand / "libggml-cpu.so.0").symlink_to(mm.CPU)
    r["candidate_cpu_sha256"] = sha(cand / mm.CPU)
    need(
        r["candidate_cpu_sha256"] not in (mm.CPU_SHA, ref["candidate_cpu_sha256"]),
        "provider identity",
    )
    exe = out / "fixture"
    scope.run(
        [
            "/usr/bin/g++-15",
            "-std=c++17",
            "-O2",
            "-pthread",
            "-fPIC",
            "-pie",
            "-fno-plt",
            "-I" + str(backend / "ggml/include"),
            "-I" + str(backend / "ggml/src"),
            "-I" + str(backend / "vendor"),
            HERE / "fixture.cpp",
            libs / mm.CPU,
            libs / mm.BASE,
            "-ldl",
            "-o",
            exe,
        ],
        env,
        out / "fixture-compile",
        c,
        r,
    )
    r["fixture_executable_sha256"] = sha(exe)
    original = None
    gold = None
    for mode in MODES:
        dir_cpu = libs if mode == "original" else cand
        env = mm.ENV | {
            "LD_LIBRARY_PATH": f"{dir_cpu}:{libs}",
            "LD_BIND_NOW": "1",
            "TESY_CPU_WAVE_SKIP_PARKED": "1",
            "OMP_NUM_THREADS": "8",
        }
        if mode != "original":
            env |= {
                "TESY_CPU_MMX_ALL_PARKED": str(int(mode != "off")),
                "TESY_CPU_PARKED_FUSION": str(int(mode == "fusion")),
            }
        mapped = mm.loader(
            exe,
            env,
            {
                "libggml-cpu.so.0": (dir_cpu / mm.CPU).resolve(),
                "libggml-base.so.0": (libs / mm.BASE).resolve(),
            },
        )
        dest = out / (mode + ".f32")
        scope.run([exe, mode, dest], env, out / mode, c, r)
        row = json.loads((out / (mode + ".stdout")).read_bytes())
        data = dest.read_bytes()
        parts = checked_parts(row, data, mode)
        check_population(row, parts, mode)
        if mode == "original":
            original, gold = parts, data
        r["arms"][mode] = {
            "providers": mapped,
            "output_sha256": sha(dest),
            "bytes": len(data),
            "raw_json_sha256": sha(out / (mode + ".stdout")),
            "cases": parts,
            "fusion_count": row["fused_regions"],
            "mode": mode,
        }
        failure = compare_cases(parts, data, original, gold, mode)
        if failure:
            r["first_difference"] = failure
            if mode == "fusion" and not (failure["reason"] == "branch" and not failure["observed"]):
                r["decision"] = "NO_GO_EXACTNESS"
            return
    r.update(status="PASS_PARKED_FUSION_NUMERICAL_FAMILY", decision="GO_REAL_TILE")


def compact_report(raw, raw_path):
    """Retain one copy of each common case digest, plus explicit counter deltas per mode."""
    keys = (
        "status",
        "decision",
        "commit",
        "tree",
        "c269_commit",
        "c55_sha256",
        "mmid_build_sha256",
        "source_sha256",
        "dependencies",
        "link_inputs_sha256",
        "original_cpu_sha256",
        "candidate_cpu_sha256",
        "base_sha256",
        "source_mmid_sha256",
        "source_fusion_sha256",
        "fixture_executable_sha256",
        "first_difference",
        "elapsed_family_s",
        "cap_bytes",
        "stop_bytes",
        "memory_peak_bytes",
        "swap_bytes",
        "memory_events",
        "max_child_rss_kib",
        "weight_input_bytes",
        "target_forwards",
        "gpu_compute",
    )
    result = {k: raw[k] for k in keys if k in raw}
    result.update(
        raw_receipt_sha256=sha(raw_path),
        raw_receipt_bytes=raw_path.stat().st_size,
        complete_modes=[m for m in MODES if m in raw["arms"]],
        not_run=[m for m in MODES if m not in raw["arms"]],
        last_command_phase=raw["last_command_phase"],
        arms={},
        cases=[],
    )
    gold = raw["arms"].get("original", {}).get("cases", [])
    result["cases"] = [{k: case[k] for k in ("id", "bytes", "sha256")} for case in gold]
    for mode in result["complete_modes"]:
        arm = raw["arms"][mode]
        cases = arm["cases"]
        result["arms"][mode] = {
            k: arm[k] for k in ("bytes", "output_sha256", "fusion_count", "raw_json_sha256")
        }
        result["arms"][mode].update(
            case_count=len(cases),
            bitwise_by_case=[c["sha256"] == g["sha256"] for c, g in zip(cases, gold, strict=True)],
            counter_expected=[c["expected_fusions"] for c in cases],
            counter_observed=[c["observed_fusions"] for c in cases],
            first_nonfinite_by_case=[c["first_nonfinite_index"] for c in cases],
        )
    return result


def verify_outputs(directory):
    """Recompute the compact and every completed case from the four private numerical streams."""
    directory = directory.resolve(strict=True)
    path = directory / "receipt.json"
    report = json.loads(path.read_bytes())
    compact = json.loads((directory / "compact.json").read_bytes())
    need(compact == compact_report(report, path), "compact/receipt mismatch")
    modes = [m for m in MODES if m in report["arms"]]
    need(modes == list(MODES[: len(modes)]), "non-prefix family")
    found = None
    gold = reference = None
    for mode in modes:
        arm = report["arms"][mode]
        stdout = directory / (mode + ".stdout")
        dest = directory / (mode + ".f32")
        need(
            sha(stdout) == arm["raw_json_sha256"] and sha(dest) == arm["output_sha256"],
            "raw digest",
        )
        row = json.loads(stdout.read_bytes())
        data = dest.read_bytes()
        parts = checked_parts(row, data, mode)
        check_population(row, parts, mode)
        need(parts == arm["cases"] and len(data) == arm["bytes"], "raw cases")
        if mode == "original":
            gold, reference = data, parts
        found = compare_cases(parts, data, reference, gold, mode)
        need(not found or mode == modes[-1], "continued after discrepancy")
    need(found == report.get("first_difference"), "unreported discrepancy")
    if report["decision"] == "GO_REAL_TILE":
        need(
            len(modes) == 4
            and found is None
            and report["status"] == "PASS_PARKED_FUSION_NUMERICAL_FAMILY",
            "incomplete numerical success",
        )
    print("REPRODUCED", report["status"], report["decision"], sha(path))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--verify-output-dir":
        verify_outputs(Path(sys.argv[2]))
        return 0
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("repo", "backend", "mmid-build", "c55-receipt", "new-output-dir"):
        p.add_argument("--" + n, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir = a.new_output_dir.resolve()
    a.new_output_dir.mkdir(mode=0o700)
    r = {
        "status": "FAIL_PRESERVED",
        "decision": "INCONCLUSIVE",
        "commands": {},
        "arms": {},
        "cap_bytes": 4 << 30,
        "stop_bytes": 7 << 29,
        "weight_input_bytes": 0,
        "gpu_compute": False,
        "target_forwards": 0,
    }
    start = time.monotonic()
    try:
        build(a, r)
    except (OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError) as err:
        r["failure"] = str(err)
    try:
        _, supervisor = old_modules()
        c = supervisor.cgroup()
        r.update(
            memory_peak_bytes=int((c / "memory.peak").read_text()),
            memory_events=supervisor.validate_events(c),
            swap_bytes=int((c / "memory.swap.current").read_text()),
        )
    except (OSError, ValueError) as err:
        r.update(status="FAIL_PRESERVED", decision="INCONCLUSIVE", resource_failure=str(err))
    r["elapsed_family_s"] = time.monotonic() - start
    r["max_child_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    r["last_command_phase"] = next(reversed(r["commands"]), None)
    dest = a.new_output_dir / "receipt.json"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    tmp.rename(dest)
    (a.new_output_dir / "compact.json").write_text(
        json.dumps(compact_report(r, dest), indent=2) + "\n"
    )
    print(r["status"], r["decision"], sha(dest))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
