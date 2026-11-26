"""Qualify ordered e28 gate and up against a shared file backing and a real e24 replacement."""

import argparse
import hashlib
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
Q = "c26244654f971c944790a667a90cbadf1955f01b8eefa4df8bda9044cfd32f23"
W = 13221888
ROLE = 4406400
ROW = 11520
CASES = (("gate", 0, "e28-gate"), ("up", 0, "e28-up"), ("gate", 1, "e24-gate"))


def golds(a):
    f = a.cpu_dir / "receipt.json"
    need(sha(f) == a.cpu_sha256, "CPU receipt")
    c = json.loads(f.read_bytes())
    need(c["status"] == "PASS_CPU0_RANK_STAGES_REFERENCE", "CPU family")
    ref = c["arm"]["rank"]
    need(
        ref["status"] == "PASS_CPU0_RANK_STAGES_REVIEW"
        and ref["logical"] == [28, 24, 8, 16]
        and ref["physical"] == [3, 14, 6, 35]
        and ref["generations"] == [6, 6, 5, 4],
        "rank authority",
    )
    result = {}
    for stage, r, n in CASES:
        blob = (a.cpu_dir / "ALIAS/rank" / (stage + ".f32")).read_bytes()
        need(
            len(blob) == 4 * ROW
            and hashlib.sha256(blob).hexdigest() == ref["files_sha256"][stage + ".f32"],
            "complete CPU stage",
        )
        row = blob[r * ROW : (r + 1) * ROW]
        need(hashlib.sha256(row).hexdigest() == ref["row_sha256"][stage][r], "CPU rank offset")
        result[n] = row
    return result


def assess(actual, gold):
    need(actual.keys() == gold.keys() == {n for _, _, n in CASES}, "three named projections")
    rows = {}
    for name, wanted in gold.items():
        data = actual[name]
        need(len(data) == len(wanted) == ROW, "F32 shape")
        x = struct.unpack("<2880f", data)
        y = struct.unpack("<2880f", wanted)
        need(all(map(math.isfinite, x)) and all(map(math.isfinite, y)), "finitude")
        diffs = [
            i
            for i, (a, b) in enumerate(
                zip(struct.iter_unpack("<I", data), struct.iter_unpack("<I", wanted), strict=True)
            )
            if a != b
        ]
        rows[name] = dict(
            unequal=len(diffs),
            max_abs=max(
                abs(actual_value - expected) for actual_value, expected in zip(x, y, strict=True)
            ),
            first_different=next(iter(diffs), None),
            sha256=hashlib.sha256(data).hexdigest(),
            gold_sha256=hashlib.sha256(wanted).hexdigest(),
        )
    need(
        actual["e28-gate"] != actual["e24-gate"] and gold["e28-gate"] != gold["e24-gate"],
        "replacement distinguished",
    )
    return dict(
        rows=rows,
        decision="NO_GO_BITWISE_ROLE"
        if any(v["unequal"] for v in rows.values())
        else "GO_BACKING_AND_TWO_ROLES_ONLY",
    )


def journal(raw):
    lines = [v.split("\t") for v in raw.splitlines()]
    need(lines and lines[-1] == ["PASS_RANK_BACKING_DISPATCH"], "native terminal")

    def rows(key):
        return [r[1:] for r in lines if r[0] == key]

    need(
        rows("device")[0][1:] == ["radv", "0000:c5:00.0", "4098", "5390", "1", "4096"]
        and rows("providers") == [["RADV+loader+renderD128"]] * 2
        and rows("variant") == [["subgroup", "1", "1", "64", "12", "2880"]]
        and int(rows("queue")[0][1]) & 2,
        "Radeon deployment",
    )
    need(len(rows("import")) == 4, "RHS/IDs/output small imports without GPU staging of weights")
    for size, align, h, b, t, heap, flags in rows("import"):
        need(
            int(size) == 65536
            and int(align) > 0
            and [t, heap, flags] in rows("type")
            and int(h) & int(b) & (1 << int(t))
            and int(flags) & 6 == 6,
            "small import",
        )
    pub = [[int(i) for i in row] for row in rows("publish")]
    need(len(pub) == 2, "two generation publications")
    inode1, inode2 = pub[0][3], pub[1][3]
    need(inode1 != inode2 and min(inode1, inode2) > 0, "two distinct file backings")
    need(
        pub == [[3, 28, 6, inode1, W, 371245056, 3 * W], [3, 24, 7, inode2, W, 318210048, 3 * W]],
        "source, generation, VA offset",
    )
    imps = [[int(i) for i in row] for row in rows("window_import")]
    need(len(imps) == 2, "two imports")
    for v, gen, ino in zip(imps, (6, 7), (inode1, inode2), strict=True):
        g, n, sz, req, base_alignment, descriptor_alignment, t, h, b, flags = v
        need(
            (g, n, sz) == (gen, ino, W)
            and 0 < req <= W
            and base_alignment > 0
            and 0 < descriptor_alignment
            and (2 * ROLE) % descriptor_alignment == 0
            and h & b & (1 << t)
            and flags & 6 == 6,
            "window bounds and storage offset",
        )
    seq = [
        r
        for r in lines
        if r[0]
        in {
            "acquire",
            "blocked_replacement",
            "role_result",
            "release_after_fence",
            "stale_rejected",
            "publish",
        }
    ]
    orders = [
        ["publish", *pub[0]],
        ["acquire", 3, 6, inode1],
        ["blocked_replacement", 6, 7],
        ["role_result", 28, 6, 0, inode1, 0, 0, ROW],
        ["role_result", 28, 6, 2, inode1, 2 * ROLE, 0, ROW],
        ["release_after_fence", 6, inode1],
        ["publish", *pub[1]],
        ["stale_rejected", 3, 6, 7],
        ["acquire", 3, 7, inode2],
        ["role_result", 24, 7, 0, inode2, 0, 0, ROW],
        ["release_after_fence", 7, inode2],
    ]
    need(seq == [[str(i) for i in r] for r in orders], "last-reader, slots and role order")
    peaks = [int(v[0]) for v in rows("scope_peak_bytes")]
    need(len(peaks) == 2 and 0 < max(peaks) <= 128 << 20, "scope peak")
    return dict(
        dispatches=4,
        generations=[6, 7],
        pack_read_bytes=2 * W,
        pack_reads=2,
        number_of_backing_fds=2,
        cpu_slot=3,
        cpu_slot_relative_offset=3 * W,
        memfd_bytes_each=W,
        min_storage_offset_alignment=imps[0][5],
        vulkan_requirement_bytes=[v[3] for v in imps],
        memory_types=[v[6] for v in imps],
        binding_offsets=[0, 2 * ROLE, 0],
        shader_local_ids=[0, 0, 0],
        scope_peak_bytes=max(peaks),
        blocked_replacement=1,
        rejected_stale_lease=1,
        per_generation_last_reader_fences=[2, 1],
    )


def run(a, out):
    info = a.build_dir / "receipt.json"
    need(sha(info) == a.build_sha256, "build receipt")
    b = json.loads(info.read_bytes())
    need(
        b["status"] == "PASS_RANK_BACKING_BUILD_ONLY" and b["inputs"] == B["pins"](), "frozen build"
    )
    for n, h in b["files"].items():
        need(sha(a.build_dir / n) == h, "artefact " + n)
    initial = golds(a)
    x = a.reference_dir / "attn_post_norm.bin"
    need(
        sha(x) == X
        and sha(a.reference_dir / "plan.json")
        == "1f1caaba34f4581f253691feee436358a8e3bcb2c67b5fd489418f52176510f1",
        "C127/C270 bundle",
    )
    unit = "tesy-igpu-rank-" + out.name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "scope identity")
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
        str(a.build_dir / "rank"),
        str(x),
        str(a.build_dir / "shared.spv"),
        str(a.build_dir / "subgroup.spv"),
        str(out / "actual.q8_1"),
        str(a.pack),
        str(a.build_dir / "gate.spv"),
        *[str(out / (n + ".f32")) for _, _, n in CASES],
    ]
    save(out / "before.json", BASE["inventory"]())
    start = time.monotonic_ns()
    with (out / "native.tsv").open("xb") as std, (out / "native.stderr").open("xb") as err:
        r = subprocess.run(args, stdout=std, stderr=err, timeout=15, check=False)
    elapsed = time.monotonic_ns() - start
    save(out / "after.json", BASE["inventory"]())
    state = subprocess.run(
        ["systemctl", "--user", "show", unit + ".scope", "-p", "ActiveState", "-p", "SubState"],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    need(
        "ActiveState=inactive" in state.stdout and "SubState=dead" in state.stdout, "scope cleanup"
    )
    raw = (out / "native.tsv").read_text()
    if r.returncode == 3 and raw.splitlines()[-1].startswith("NOT_ADMITTED\t"):
        return dict(
            status="NOT_ADMITTED_FILE_BACKING",
            reason=raw.splitlines()[-1],
            limits=[r for r in raw.splitlines() if r.startswith("unsupported_size\t")],
            wall_ns=elapsed,
        )
    need(r.returncode == 0, "native exit " + str(r.returncode) + " see native.tsv/stderr")
    proof = journal(raw)
    need(
        sha(out / "actual.q8_1") == Q and sha(x) == X and initial == golds(a), "RHS or gold changed"
    )
    result = assess({n: (out / (n + ".f32")).read_bytes() for _, _, n in CASES}, initial)
    return dict(
        status="MEASURED_RANK_BACKING_AND_ROLES",
        build_sha256=a.build_sha256,
        cpu_receipt_sha256=a.cpu_sha256,
        input_sha256=X,
        rhs_sha256=Q,
        ordered_module_sha256=B["ORDERED_SPV"],
        proof=proof,
        result=result,
        scope_after=state.stdout.splitlines(),
        wall_ns=elapsed,
        model_forwards=0,
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
    print(row["status"], row.get("result", {}), row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
