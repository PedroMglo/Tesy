"""Build and dispatch the C269 Q8_1 witness on the previously qualified RADV station."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(HERE.parent / "run.py")
sha, need, save = (BASE[name] for name in ("sha", "need", "save"))
PROTOCOL = "e401de9c39a56c57197f58d77e962780eabdfb9d9ef1e397c13e3cae8e7708b8"
PRIOR = "282d56fb8fa99c4b3bad7171318ebc47aeb1df92b2eaa2bb6a22f78979c3cc93"
ORACLE = "56ed61a33abcf79b3673beffbc62f6bc2a4fcdb44145909a8a9369da85750a6e"
HOST = "e3b597aec590fae2eefb556e5c654ccdf528078bcc7a585ed20ba854a95a8c8d"


def seals():
    previous = BASE["seals"]()
    need(previous["native"] == HOST, "host native gate changed")
    need(sha(HERE / "protocol.md") == PROTOCOL, "RHS protocol")
    need(sha(HERE.parent / "evidence/receipt.json") == PRIOR, "previous import gate")
    need(sha(HERE.parent / "rhs/receipt.json") == ORACLE, "independent source witnesses")
    return dict(
        deployment=previous,
        protocol=PROTOCOL,
        import_receipt=PRIOR,
        prior_rhs=ORACLE,
        sources={
            n: sha(HERE / n) for n in ("run.py", "compile_shader.py", "dispatch.cpp", "oracle.py")
        },
    )


def prepare_host(out):
    """Retain the complete predecessor identity/import checks with two 64-KiB buffers."""
    path = HERE.parent / "host_import.cpp"
    need(sha(path) == HOST, "host source")
    prefix, rest = path.read_text().split("uint32_t word(", 1)
    need(prefix.count("3 * 4406400") == 1, "payload constant")
    (out / "host-functions.inc").write_text(prefix.replace("3 * 4406400", "2880 * sizeof(float)"))
    acquire = rest.split("void run() {\n", 1)[1].split("    const char *extension=", 1)[0]
    need("guard();" in acquire and "qc.pQueuePriorities=&prio;" in acquire, "device gate span")
    (out / "host-acquire.inc").write_text(acquire)


def build(a, out):
    need(
        all(sha(a.headers / "vulkan" / n) == h for n, h in BASE["HEADERS"].items()),
        "Khronos headers",
    )
    modules = run_path(HERE / "compile_shader.py")["compile_modules"](a.backend, out)
    prepare_host(out)
    (out / "input.f32").write_bytes(run_path(HERE / "oracle.py")["inputs"]())
    opts = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers"]
    args = [
        str(BASE["CXX"]),
        *opts,
        "-I",
        str(a.headers),
        "-I",
        str(out),
        str(HERE / "dispatch.cpp"),
        str(BASE["LOADER"]),
        "-o",
        str(out / "dispatch"),
    ]
    with (out / "build.log").open("xb") as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=25)
    files = [
        "dispatch",
        "input.f32",
        "shared.spv",
        "subgroup.spv",
        "host-functions.inc",
        "host-acquire.inc",
        "build.log",
    ]
    return dict(
        status="PASS_RHS_BUILD_ONLY",
        files={n: sha(out / n) for n in files},
        cxx_sha256=sha(BASE["CXX"]),
        headers=BASE["HEADERS"],
        compiler_options=opts,
        modules=modules,
        gpu_processes=0,
    )


def review(raw):
    lines = [s.split("\t") for s in raw.splitlines()]
    need(lines and lines[-1] == ["PASS_RHS_DISPATCH"], "native terminal")
    fields = {}
    for key, *values in lines[:-1]:
        fields.setdefault(key, []).append(values)

    def one(key):
        (values,) = fields[key]
        return values

    dev = one("device")
    need(dev[1:6] == ["radv", "0000:c5:00.0", "4098", "5390", "1"], "deployment")
    need(int(dev[6]) == 4096 and int(one("external_features")[0]) & 4, "import support")
    need(fields["providers"] == [["RADV+loader+renderD128"]] * 2, "live providers")
    need(int(one("queue")[1]) & 2, "compute queue")
    imports = [list(map(int, r)) for r in fields["import"]]
    types = {int(t): (int(h), int(f)) for t, h, f in fields["type"]}
    need(len(imports) == 2, "two imports")
    for n, alignment, pointers, buffers, t, h, flags in imports:
        need(
            11520 <= n <= (16 << 20)
            and n % 4096 == 0
            and alignment > 0
            and flags & 6 == 6
            and types[t] == (h, flags)
            and pointers & buffers & (1 << t),
            "coherent compatible import",
        )
    peaks = [int(r[0]) for r in fields["scope_peak_bytes"]]
    need(len(peaks) == 2 and 0 < max(peaks) <= BASE["CAP"], "scope peak")
    variant, *values = one("variant")
    clustered, full, group, count, width = map(int, values)
    need(
        group in (32, 64)
        and width == 2880
        and count == (width + 4 * group - 1) // (4 * group)
        and clustered in (0, 1)
        and full in (0, 1)
        and variant == ("subgroup" if clustered and full else "shared"),
        "variant and launch geometry",
    )
    fence = int(one("submit_fence_ns")[0])
    need(fence > 0, "submit/fence clock")
    return dict(
        device=dev[0],
        pci=dev[2],
        variant=variant,
        clustered=bool(clustered),
        compute_full_subgroups=bool(full),
        specialization_id_0=group,
        workgroups=count,
        push_constants=[width, count],
        host_imports=imports,
        submit_to_observed_fence_ns=fence,
        scope_peak_bytes=max(peaks),
        dispatches=1,
        model_forwards=0,
    )


def run(a, out):
    root = a.build_dir.resolve()
    receipt = root / "receipt.json"
    need(sha(receipt) == a.build_sha256, "build receipt")
    b = json.loads(receipt.read_bytes())
    need(b["status"] == "PASS_RHS_BUILD_ONLY" and b["inputs"] == seals(), "frozen checkout")
    for name, digest in b["files"].items():
        need(sha(root / name) == digest, "build artefact " + name)
    save(out / "before.json", BASE["inventory"]())
    layers = out / "empty-layers"
    layers.mkdir()
    unit = "tesy-igpu-rank-" + out.name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "unit")
    env = [
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "VK_DRIVER_FILES=" + str(BASE["ICD"]),
        "VK_LAYER_PATH=" + str(layers),
        "VK_IMPLICIT_LAYER_PATH=" + str(layers),
        "VK_LOADER_LAYERS_DISABLE=~implicit~",
        "MESA_SHADER_CACHE_DISABLE=true",
    ]
    args = [
        "/usr/bin/systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--unit",
        unit,
        "-p",
        "MemoryMax=134217728",
        "-p",
        "MemoryHigh=134217728",
        "-p",
        "MemorySwapMax=0",
        "--",
        "/usr/bin/env",
        "-i",
        *env,
        "/usr/bin/timeout",
        "-k",
        "1s",
        "9s",
        str(root / "dispatch"),
        str(root / "input.f32"),
        str(root / "shared.spv"),
        str(root / "subgroup.spv"),
        str(out / "actual.q8_1"),
    ]
    start = time.monotonic_ns()
    with (out / "native.tsv").open("xb") as stdout, (out / "native.stderr").open("xb") as stderr:
        child = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=15, check=False)
    wall = time.monotonic_ns() - start
    save(out / "after.json", BASE["inventory"]())
    raw = (out / "native.tsv").read_text()
    state = subprocess.run(
        ["systemctl", "--user", "show", unit + ".scope", "-p", "ActiveState", "-p", "SubState"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    need(
        "ActiveState=inactive" in state.stdout and "SubState=dead" in state.stdout, "scope cleanup"
    )
    if child.returncode == 3 and raw.splitlines()[-1].startswith("NOT_ADMITTED\t"):
        return dict(status="NOT_ADMITTED_RHS", reason=raw.splitlines()[-1], wall_ns=wall)
    need(child.returncode == 0, f"native exit {child.returncode}; see native.tsv and native.stderr")
    proof = review(raw)
    grade = run_path(HERE / "oracle.py")["grade"]((out / "actual.q8_1").read_bytes())
    need(grade["input_sha256"] == sha(root / "input.f32"), "reference input bytes")
    return dict(
        status="PASS_RADV_Q8_1_WITNESS",
        grade=grade,
        proof=proof,
        wall_ns=wall,
        build_sha256=a.build_sha256,
        device_scope=unit + ".scope",
        scope_after=state.stdout.splitlines(),
        selected_module_sha256=sha(root / (proof["variant"] + ".spv")),
        files={
            n: sha(out / n)
            for n in ("native.tsv", "native.stderr", "before.json", "after.json", "actual.q8_1")
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--headers", type=Path)
    parser.add_argument("--backend", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--build-sha256")
    parser.add_argument("--new-output-dir", type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    try:
        inputs = seals()
        row = build(a, out) if a.build else run(a, out)
        row["inputs"] = inputs
    except Exception as e:
        row = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    save(out / "receipt.json", row)
    print(row["status"], row.get("reason", ""))
    return int(row["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
