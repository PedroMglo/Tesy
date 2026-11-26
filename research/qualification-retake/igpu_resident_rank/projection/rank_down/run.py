"""Authenticate real Radeon SwiGLU, subrange readers and the e28 pre-bias CPU reference."""

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
P = run_path(B["PRIMARY"] / "run.py")
BASE, need, sha, save = (B[k] for k in ("BASE", "need", "sha", "save"))
PRIMARY = "66d7f6f83252ffa0290ac1c712a5a2fc09bd9c27a08ed81796a4963a79fd6449"
SWIGLU = "1c7fa886160b01c8f2eb0ce883faf5db666fbc00a04586c694d63ef520df4cd6"
CPU = "3ef107129e6d4c7afb755ac5836c9099b37a37f3eb3ab87f25fed3e9ba28dd53"
X = "1fbf0b978b0a992526a0f13427ba86412569bff28f33429903b05e9d5cf2d8d3"
Q = "6215822f56ad6d4c855433a44997aa5802ce0f487c224e89b3607b31c8b1fcfa"
S = 4406400
T = 40 * S


def checked(path, digest):
    need(sha(path) == digest, "authority " + path.name)
    return json.loads(path.read_bytes())


def upstream(a):
    primary = checked(a.primary_dir / "receipt.json", PRIMARY)
    swiglu = checked(a.swiglu_dir / "receipt.json", SWIGLU)
    cpu = checked(a.cpu_dir / "receipt.json", CPU)
    rank = cpu["arm"]["rank"]
    need(
        primary["result"]["decision"] == "GO_DENSE_GGML_PRIMARY_GATE_UP_ONLY"
        and swiglu["result"]["decision"] == "EQUAL_EFFECTIVE_DOWN_OPERAND_ONLY"
        and primary["cpu_sha256"] == swiglu["cpu_receipt_sha256"] == CPU
        and cpu["status"] == "PASS_CPU0_RANK_STAGES_REFERENCE"
        and rank["physical"] == [3, 14, 6, 35]
        and rank["logical"] == [28, 24, 8, 16]
        and rank["generations"] == [6, 6, 5, 4],
        "upstream decisions/cut",
    )
    for role, index in (("gate", 0), ("up", 0), ("gate", 1)):
        n = f"e{rank['logical'][index]}-{role}"
        need(
            sha(a.primary_dir / (n + ".f32"))
            == primary["result"]["rows"][n]["sha256"]
            == rank["row_sha256"][role][index],
            "primary result " + n,
        )
    for k in ("gate-biased", "up-biased"):
        need(swiglu["inputs"][k] == rank["row_sha256"][k][0], "SwiGLU biased operand " + k)
    jobs = [j for j in swiglu["jobs"] if j["name"] == "q8"]
    need(
        len(jobs) == 1
        and sha(a.swiglu_dir / "swiglu.f32")
        == swiglu["swiglu_sha256"]
        == jobs[0]["input_sha256"]
        == X
        and sha(a.swiglu_dir / "q8/actual.bin") == jobs[0]["files"]["actual.bin"] == Q,
        "physical RHS",
    )
    down = a.cpu_dir / "ALIAS/rank/down.f32"
    need(
        sha(down) == rank["files_sha256"]["down.f32"] and down.stat().st_size == 4 * 11520,
        "CPU full down",
    )
    gold = down.read_bytes()[:11520]
    need(hashlib.sha256(gold).hexdigest() == rank["row_sha256"]["down"][0], "CPU down e28")
    return gold


def assess(y, control, gold):
    for x in (y, control, gold):
        need(
            len(x) == 11520 and all(map(math.isfinite, struct.unpack("<2880f", x))),
            "finite complete projections",
        )

    def different(a, b):
        return [i for i in range(2880) if a[4 * i : 4 * i + 4] != b[4 * i : 4 * i + 4]]

    diff = different(y, gold)
    cf = different(y, control)
    need(cf, "unchanged alternate physical slot")
    return dict(
        differences=len(diff),
        first_different=next(iter(diff), None),
        control_changed_words=len(cf),
        gold_sha256=hashlib.sha256(gold).hexdigest(),
        decision="NO_GO_RANK_DOWN_BITWISE" if diff else "GO_RANK_DOWN_ONLY",
    )


def journal(raw):
    lines = [r.split("\t") for r in raw.splitlines()]

    def rows(k):
        return [v[1:] for v in lines if v[0] == k]

    def nums(k):
        return [list(map(int, v)) for v in rows(k)]

    need(
        lines[-1] == ["PASS_RANK_DOWN"]
        and rows("providers") == [["RADV+loader+renderD128"]] * 2
        and rows("variant") == [["subgroup", "1", "1", "64", "12", "2880"]]
        and rows("device")[0][1:] == ["radv", "0000:c5:00.0", "4098", "5390", "1", "4096"],
        "Radeon and native return",
    )
    ts = nums("ggml_tensor")
    need(len(ts) == 3 and [v[0] for v in ts] == [0, 1, 2], "dense primary roles")
    size = ts[0][3]
    need(3 * T <= size <= 3 * T + 4096, "GGML primary")
    for k, off, n, owner, base_mod, tensor_mod in ts:
        need(
            owner == size
            and n == T
            and off >= k * T
            and off + T <= owner
            and base_mod % 64 == 0
            and tensor_mod == (base_mod + off) % 4096,
            "GGML tensor range",
        )
    need(nums("ggml_set") == [[28, 3, 1, 375651456, S], [24, 14, 1, 322616448, S]], "DOWN only")
    ranges = nums("primary_range")
    need(
        len(ranges) == 2 and nums("released") == [[28, 3, 1, 0, 11520], [24, 14, 1, 0, 11520]],
        "two releases",
    )
    sequence = [(r[0], *map(int, r[1:4])) for r in lines if r[0] in ("primary_range", "released")]
    need(
        sequence
        == [(k, e, s, 1) for e, s in ((28, 3), (24, 14)) for k in ("primary_range", "released")],
        "lease sequencing",
    )
    for (e, slot), r in zip(((28, 3), (24, 14)), ranges, strict=True):
        x, s, role, page, d, n, req, alloc, align, typ, hbits, bbits = r
        need(
            (x, s, role) == (e, slot, 1)
            and page + d == ts[1][1] + slot * S
            and (ts[1][4] + page) % 4096 == 0
            and 0 <= d < 4096
            and n == S + d
            and 0 <= page
            and page + alloc <= size
            and n <= req <= alloc
            and alloc % 4096 == 0
            and align > 0
            and d % align == 0
            and hbits & bbits & (1 << typ),
            "selected DOWN subrange",
        )
    peaks = [v[0] for v in nums("scope_peak_bytes")]
    need(len(peaks) == 3 and 0 < max(peaks) <= 128 << 20, "memory cap")
    return dict(
        ggml_bytes=size, peak_bytes=max(peaks), primary_set_bytes=2 * S, ranges=ranges, dispatches=3
    )


def run(a, out):
    build = checked(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["inputs"] == B["inputs"]() and build["status"] == "PASS_RANK_DOWN_BUILD",
        "source identity",
    )
    for f, h in build["files"].items():
        need(sha(a.build_dir / f) == h, "build " + f)

    def providers():
        return {k: sha(Path(v)) for k, v in build["providers"].items()}

    need(providers() == B["P"]["DSOS"], "CPU libraries")
    gold = upstream(a)
    unit = "tesy-igpu-rank-" + out.name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "scope")
    layer = out / "empty-layers"
    layer.mkdir()
    cmd = [
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
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "OMP_NUM_THREADS=1",
        "VK_DRIVER_FILES=" + str(BASE["ICD"]),
        "VK_LAYER_PATH=" + str(layer),
        "VK_IMPLICIT_LAYER_PATH=" + str(layer),
        "VK_LOADER_LAYERS_DISABLE=~implicit~",
        "MESA_SHADER_CACHE_DISABLE=true",
        "/usr/bin/timeout",
        "-k",
        "1s",
        "9s",
        str(a.build_dir / "rank"),
        str(a.swiglu_dir / "swiglu.f32"),
        str(a.build_dir / "shared.spv"),
        str(a.build_dir / "subgroup.spv"),
        str(out / "actual.q8_1"),
        str(a.pack),
        str(a.build_dir / "gate.spv"),
        str(out / "e28-down.f32"),
        str(out / "e24-down.f32"),
    ]
    save(out / "before.json", BASE["inventory"]())
    tic = time.monotonic_ns()
    with (out / "native.tsv").open("xb") as log, (out / "native.stderr").open("xb") as err:
        child = subprocess.run(cmd, stdout=log, stderr=err, timeout=15, check=False)
    wall = time.monotonic_ns() - tic
    save(out / "after.json", BASE["inventory"]())
    state = subprocess.run(
        ["systemctl", "--user", "show", unit + ".scope", "-p", "ActiveState", "-p", "SubState"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    ).stdout.splitlines()
    need({"ActiveState=inactive", "SubState=dead"} <= set(state), "scope inactive")
    raw = (out / "native.tsv").read_text()
    common = dict(
        scope_after=state,
        wall_ns=wall,
        model_forwards=0,
        build_sha256=a.build_sha256,
        primary_sha256=PRIMARY,
        swiglu_sha256=SWIGLU,
        cpu_sha256=CPU,
        input_swiglu_f32_sha256=X,
        expected_q8_sha256=Q,
        files={f.name: sha(f) for f in sorted(out.iterdir()) if f.is_file()},
    )
    if child.returncode == 3 and raw.splitlines()[-1].startswith("NOT_ADMITTED\t"):
        return dict(common, status="NOT_ADMITTED_GGML_DOWN", reason=raw.splitlines()[-1])
    need(child.returncode == 0, "native exit " + str(child.returncode))
    proof = journal(raw)
    need(providers() == B["P"]["DSOS"] and upstream(a) == gold, "postflight identities")
    actual = (out / "actual.q8_1").read_bytes()
    expected = (a.swiglu_dir / "q8/actual.bin").read_bytes()
    need(len(actual) == len(expected) == 3312, "Q8 length")
    result = assess((out / "e28-down.f32").read_bytes(), (out / "e24-down.f32").read_bytes(), gold)
    result["q8_different_bytes"] = sum(x != y for x, y in zip(actual, expected, strict=True))
    if result["q8_different_bytes"]:
        result["decision"] = "NO_GO_RANK_DOWN_RHS"
    return dict(common, status="MEASURED_RADV_RANK_DOWN", proof=proof, result=result)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("build-dir", "cpu-dir", "primary-dir", "swiglu-dir", "pack", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    p.add_argument("--build-sha256", required=True)
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
