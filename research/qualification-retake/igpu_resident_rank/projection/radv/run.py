"""One supervised RADV job for e28. The native process sees neither CPU projection nor gold."""

import argparse
import json
import math
import os
import struct
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(HERE / "build.py")
BASE, sha, need, save = (B[k] for k in ("BASE", "sha", "need", "save"))
X = "f4b7b1fc1595244c263e292a8cd2d6c1d3c939e00b56e151c5c5d48fc403092e"
WEIGHT = "3a76d368a4c215dafd9d39e740d1db137709d8bac6df70084c918656ec31cc50"
PLAN = "1f1caaba34f4581f253691feee436358a8e3bcb2c67b5fd489418f52176510f1"


def compare(correct, wrong, gold, q8, cpu_q8):
    need(
        len(correct) == len(wrong) == len(gold) == 11520
        and len(q8) == 3312
        and len(cpu_q8) == 3060,
        "raw sizes",
    )
    xf = struct.unpack("<2880f", correct)
    yf = struct.unpack("<2880f", gold)
    need(all(math.isfinite(x) for x in [*xf, *yf]), "nonfinite gate")
    need(
        any(v != 0 for v in xf) and all(v[0] == 0 for v in struct.iter_unpack("<f", wrong)),
        "wrong-ID control",
    )
    u = struct.unpack("<2880I", correct)
    g = struct.unpack("<2880I", gold)
    mismatches = [i for i in range(len(u)) if u[i] != g[i]]

    def ordered(word):
        return (0xFFFFFFFF - word) if word >> 31 else word + (1 << 31)

    scales = []
    codes = []
    for k in range(90):
        start = 144 * (k // 4)
        a = start + 4 * (k % 4)
        b = start + 16 + 32 * (k % 4)
        if q8[a : a + 2] != cpu_q8[34 * k : 34 * k + 2]:
            scales.append(k)
        for j in range(32):
            if q8[b + j] != cpu_q8[34 * k + 2 + j]:
                codes.append([k, j])
    last = q8[-144:]
    need(last[8:16] == bytes(8) and last[80:] == bytes(64), "Q8_1 pad")
    return dict(
        finite=2880,
        unequal_rows=len(mismatches),
        first_unequal=mismatches[0] if mismatches else None,
        max_abs=max(abs(a - b) for a, b in zip(xf, yf, strict=True)),
        max_ulp=max(abs(ordered(a) - ordered(b)) for a, b in zip(u, g, strict=True)),
        wrong_exact_zeros=2880,
        q8_scale_mismatch=len(scales),
        q8_codes_mismatch=len(codes),
        first_scale_block=next(iter(scales), None),
        first_code_coordinate=next(iter(codes), None),
        decision="NO_GO_BITWISE_STOCK_PROJECTION" if mismatches else "GO_NEXT_PROJECTION_ONLY",
    )


def review(log):
    lines = [r.split("\t") for r in log.splitlines()]
    need(lines[-1] == ["PASS_RADV_PROJECTION_DISPATCH"], "dispatch terminal")

    def rows(k):
        return [r[1:] for r in lines if r[0] == k]

    need(rows("providers") == [["RADV+loader+renderD128"]] * 2, "providers")
    need(rows("weight") == [[WEIGHT, "4406400", "13219200", "371245056"]], "weight and slot stride")
    need(rows("variant") == [["subgroup", "1", "1", "64", "12", "2880"]], "RHS dispatch")
    n = rows("mmvq_admitted")
    need(
        len(n) == 1 and n[0][:2] == ["1", "1"] and int(n[0][2]) <= 64 <= int(n[0][3]),
        "signed packed dot",
    )
    need(
        rows("projection") == [[str(s), "1440", "1", "1", "64", "2", "11520"] for s in (3, 2)],
        "IDs, launches",
    )
    need(rows("device")[0][1:] == ["radv", "0000:c5:00.0", "4098", "5390", "1", "4096"], "device")
    need(
        int(rows("queue")[0][1]) & 2 and int(rows("external_features")[0][0]) & 4, "compute/import"
    )
    imports = [list(map(int, v)) for v in rows("import")]
    need(
        len(imports) == 5 and imports[2][0] >= 17625600 and sum(i[0] for i in imports) < (24 << 20),
        "buffers",
    )
    for size, alignment, pointers, buffers, t, h, f in imports:
        need(
            size % 4096 == 0
            and alignment > 0
            and pointers & buffers & (1 << t)
            and f & 6 == 6
            and [str(t), str(h), str(f)] in rows("type"),
            "pointer/buffer compatibility",
        )
    pk = [int(v[0]) for v in rows("scope_peak_bytes")]
    need(len(pk) == 2 and 0 < max(pk) <= 128 << 20, "cgroup cap")
    return dict(
        variant="mmvq-subgroup-no-shmem",
        rhs="q8_1_x4-subgroup",
        subgroup=64,
        rows_per_group=2,
        workgroups=[1440, 1, 1],
        bound_ids=[[3, 14, 6, 35], [2, 14, 6, 35]],
        dispatches=3,
        heap_types=imports,
        scope_peak_bytes=max(pk),
    )


def run(a, out):
    info = a.build_dir / "receipt.json"
    need(sha(info) == a.build_sha256, "build receipt")
    b = json.loads(info.read_bytes())
    need(
        b["status"] == "PASS_RADV_PROJECTION_BUILD_ONLY" and b["inputs"] == B["pin"](),
        "signed build inputs",
    )
    for n, h in b["files"].items():
        need(sha(a.build_dir / n) == h, "build artefact " + n)
    need(sha(a.cpu_dir / "receipt.json") == a.cpu_sha256, "independent CPU receipt")
    cpu = json.loads((a.cpu_dir / "receipt.json").read_bytes())
    need(cpu["status"] == "PASS_CPU0_E28_PROJECTION_REFERENCE", "CPU qualification")
    authority = cpu["arm"]["projection"]
    gold_dir = a.cpu_dir / "ALIAS/projection"
    need(json.loads((gold_dir / "gate.json").read_bytes()) == authority, "CPU native witness")
    need(
        authority["weight_sha256"] == WEIGHT
        and authority["x_sha256"] == X
        and authority["gate_sha256"]
        == authority["single_sha256"]
        == sha(gold_dir / "gate-rank0.f32")
        and authority["q8_sha256"] == sha(gold_dir / "activation.q8"),
        "CPU authorities",
    )
    x = a.reference_dir / "attn_post_norm.bin"
    need(sha(a.reference_dir / "plan.json") == PLAN and sha(x) == X, "part 74")
    unit = "tesy-igpu-rank-" + out.name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "scope identity")
    save(out / "before.json", BASE["inventory"]())
    layers = out / "empty-layers"
    layers.mkdir()
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
        str(a.build_dir / "projection"),
        str(x),
        str(a.build_dir / "shared.spv"),
        str(a.build_dir / "subgroup.spv"),
        str(out / "actual.q8_1"),
        str(a.pack),
        str(a.build_dir / "projection.spv"),
        str(out / "correct.f32"),
        str(out / "wrong.f32"),
    ]
    start = time.monotonic_ns()
    with (out / "native.tsv").open("xb") as stdout, (out / "native.stderr").open("xb") as stderr:
        child = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=15, check=False)
    elapsed = time.monotonic_ns() - start
    save(out / "after.json", BASE["inventory"]())
    result = subprocess.run(
        ["systemctl", "--user", "show", unit + ".scope", "-p", "ActiveState", "-p", "SubState"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    need(
        "ActiveState=inactive" in result.stdout and "SubState=dead" in result.stdout,
        "scope cleanup",
    )
    log = (out / "native.tsv").read_text()
    if child.returncode == 3 and log.splitlines()[-1].startswith("NOT_ADMITTED\t"):
        return dict(
            status="NOT_ADMITTED_RADV_PROJECTION",
            reason=log.splitlines()[-1],
            scope=result.stdout.splitlines(),
        )
    need(child.returncode == 0, f"native exit {child.returncode}, see native.tsv/stderr")
    proof = review(log)
    need(
        sha(x) == X
        and sha(gold_dir / "gate-rank0.f32") == authority["gate_sha256"]
        and sha(gold_dir / "activation.q8") == authority["q8_sha256"],
        "readback authority",
    )
    score = compare(
        *(
            p.read_bytes()
            for p in (
                out / "correct.f32",
                out / "wrong.f32",
                gold_dir / "gate-rank0.f32",
                out / "actual.q8_1",
                gold_dir / "activation.q8",
            )
        )
    )
    return dict(
        status="MEASURED_RADV_E28_PROJECTION",
        proof=proof,
        score=score,
        input_sha256=X,
        scope_after=result.stdout.splitlines(),
        wall_ns=elapsed,
        build_sha256=a.build_sha256,
        cpu_sha256=a.cpu_sha256,
        gpu_forwards=0,
        gold_sha256=authority["gate_sha256"],
        cpu_q8_sha256=authority["q8_sha256"],
        files={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()},
    )


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
    print(row["status"], row.get("score", {}), row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
