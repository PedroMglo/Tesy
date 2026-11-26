"""Compare three products that read dense, qualified GGML CPU allocations on RADV."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(HERE / "build.py")
BASE, sha, need, save = (B[k] for k in ("BASE", "sha", "need", "save"))
OLD = run_path(B["OLD"] / "run.py")
S = 4406400
T = 40 * S
STAGES = [(28, 3, 0), (28, 3, 2), (24, 14, 0)]


def journal(raw):
    lines = [r.split("\t") for r in raw.splitlines()]

    def rows(tag):
        return [r[1:] for r in lines if r[0] == tag]

    def numbers(tag):
        return [[int(i) for i in x] for x in rows(tag)]

    need(lines and lines[-1] == ["PASS_PRIMARY_CPU_IMPORT"], "native termination")
    need(rows("providers") == [["RADV+loader+renderD128"]] * 2, "Vulkan authorities")
    need(
        rows("variant") == [["subgroup", "1", "1", "64", "12", "2880"]]
        and rows("device")[0][1:] == ["radv", "0000:c5:00.0", "4098", "5390", "1", "4096"],
        "Radeon and RHS",
    )
    tensors = numbers("ggml_tensor")
    need(len(tensors) == 3 and [r[0] for r in tensors] == [0, 1, 2], "three GGML CPU tensors")
    buffer_size = tensors[0][3]
    for k, off, tn, buf, base_mod, t_mod in tensors:
        need(
            tn == T
            and buf == buffer_size
            and 3 * T <= buf <= 3 * T + 4096
            and off >= k * T
            and off + tn <= buf
            and t_mod == (base_mod + off) % 4096
            and base_mod % 64 == 0,
            "owner and tensor span",
        )
    sets = numbers("ggml_set")
    need(
        sets
        == [
            [e, s, k, start + k * S, S]
            for e, s, start in ((28, 3, 371245056), (24, 14, 318210048))
            for k in range(3)
        ],
        "GGML SET addresses and payload",
    )
    ranges = numbers("primary_range")
    need(len(ranges) == 3, "three imports")
    order = []
    for x in lines:
        if x[0] in ("primary_range", "released"):
            order.append((x[0], *[int(v) for v in x[1:4]]))
    need(
        order == [(tag, *stage) for stage in STAGES for tag in ("primary_range", "released")],
        "lease sequencing",
    )
    for stage, entry in zip(STAGES, ranges, strict=True):
        e, s, k, page, delta, requested, requirement, allocation, align, kind, hbits, bbits = entry
        need(
            (e, s, k) == stage
            and page + delta == tensors[k][1] + s * S
            and (tensors[k][4] + page) % 4096 == 0
            and 0 <= delta < 4096
            and requested == S + delta
            and 0 <= page
            and page + allocation <= buffer_size
            and requested <= requirement <= allocation
            and allocation % 4096 == 0
            and align > 0
            and delta % align == 0
            and hbits & bbits & (1 << kind),
            "imported original page and descriptor",
        )
    need(numbers("released") == [[*s, 0, 11520] for s in STAGES], "return after fence")
    peaks = [r[0] for r in numbers("scope_peak_bytes")]
    need(len(peaks) == 3 and 0 < max(peaks) <= 128 << 20, "three cgroup peak samples")
    return dict(
        ggml_owner_bytes=buffer_size,
        tensors=tensors,
        subranges=ranges,
        imports=len(ranges),
        primary_bytes_set=6 * S,
        peak_after_six_sets_bytes=peaks[1],
        peak_bytes=max(peaks),
        weight_transfers_to_dedicated_gpu_memory=0,
        dispatches=4,
    )


def run(a, out):
    need(sha(a.build_dir / "receipt.json") == a.build_sha256, "build receipt")
    build = json.loads((a.build_dir / "receipt.json").read_bytes())
    need(
        build["inputs"] == B["inputs"]() and build["status"] == "PASS_PRIMARY_BUILD_ONLY",
        "frozen source",
    )
    for n, d in build["files"].items():
        need(sha(a.build_dir / n) == d, "build file " + n)

    def dsos():
        return {k: sha(Path(path)) for k, path in build["providers"].items()}

    need(dsos() == B["DSOS"], "installed C269 DSO")
    gold = OLD["golds"](a)
    x = a.reference_dir / "attn_post_norm.bin"
    need(
        sha(x) == OLD["X"]
        and sha(a.reference_dir / "plan.json")
        == "1f1caaba34f4581f253691feee436358a8e3bcb2c67b5fd489418f52176510f1",
        "position189",
    )
    unit = "tesy-igpu-rank-" + out.name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "scope")
    layers = out / "empty-layers"
    layers.mkdir()
    env = [
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "OMP_NUM_THREADS=1",
        "VK_DRIVER_FILES=" + str(BASE["ICD"]),
        "VK_LAYER_PATH=" + str(layers),
        "VK_IMPLICIT_LAYER_PATH=" + str(layers),
        "VK_LOADER_LAYERS_DISABLE=~implicit~",
        "MESA_SHADER_CACHE_DISABLE=true",
    ]
    names = [n for _, _, n in OLD["CASES"]]
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
        str(a.build_dir / "rank"),
        str(x),
        str(a.build_dir / "shared.spv"),
        str(a.build_dir / "subgroup.spv"),
        str(out / "actual.q8_1"),
        str(a.pack),
        str(a.build_dir / "gate.spv"),
        *[str(out / (n + ".f32")) for n in names],
    ]
    save(out / "before.json", BASE["inventory"]())
    tic = time.monotonic_ns()
    with (out / "native.tsv").open("xb") as stdout, (out / "native.stderr").open("xb") as stderr:
        child = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=15, check=False)
    elapsed = time.monotonic_ns() - tic
    save(out / "after.json", BASE["inventory"]())
    state = subprocess.run(
        ["systemctl", "--user", "show", unit + ".scope", "-p", "ActiveState", "-p", "SubState"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    need("ActiveState=inactive" in state.stdout and "SubState=dead" in state.stdout, "cleanup")
    log = (out / "native.tsv").read_text()
    common = dict(
        build_sha256=a.build_sha256,
        cpu_sha256=a.cpu_sha256,
        scope_after=state.stdout.splitlines(),
        wall_ns=elapsed,
        model_forwards=0,
        files={f.name: sha(f) for f in sorted(out.iterdir()) if f.is_file()},
    )
    if child.returncode == 3 and log.splitlines()[-1].startswith("NOT_ADMITTED\t"):
        return dict(common, status="NOT_ADMITTED_GGML_PRIMARY", reason=log.splitlines()[-1])
    need(
        child.returncode == 0,
        "native exit " + str(child.returncode) + " see native.tsv and native.stderr",
    )
    proof = journal(log)
    need(
        dsos() == B["DSOS"]
        and sha(x) == OLD["X"]
        and sha(out / "actual.q8_1") == OLD["Q"]
        and OLD["golds"](a) == gold,
        "control after",
    )
    result = OLD["assess"]({n: (out / (n + ".f32")).read_bytes() for n in names}, gold)
    result["decision"] = (
        "GO_DENSE_GGML_PRIMARY_GATE_UP_ONLY"
        if all(r["unequal"] == 0 for r in result["rows"].values())
        else "NO_GO_PRIMARY_BITWISE"
    )
    return dict(common, status="MEASURED_GGML_PRIMARY_IMPORT", result=result, proof=proof)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("build-dir", "cpu-dir", "reference-dir", "pack", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    for k in ("build-sha256", "cpu-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    try:
        row = run(a, out)
    except Exception as e:
        row = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    save(out / "receipt.json", row)
    print(row["status"], row.get("result", {}), row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
