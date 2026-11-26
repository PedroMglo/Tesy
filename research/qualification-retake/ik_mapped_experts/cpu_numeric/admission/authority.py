"""Authenticate the passive C55 window, both official rows and the same-build CPU control."""

import hashlib
import json
import os
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = HERE.parents[2]
ROOT = Q.parents[1]
sys.path.insert(0, str(Q / "stock_numeric"))
import evaluate as historical  # noqa: E402

sys.path.insert(0, str(Q / "stock_startup"))
import start as stock  # noqa: E402

GIB = 1 << 30
MIB = 1 << 20
WIDTH = 201088
ROW = WIDTH * 4
PACK17 = "378eeb5ae41c80e16df38faad214c82e138727d2ddc1723a44f09c29c6e0f75c"
GOLD = (
    "da1de57d5c7f736a9156271f1f80669e040727347494b3ac3f7bba5b73e3be9b",
    "c813e8fb7e6bb5401ae800c27171fd32e0da02977c678a494d4f8f7c32cf3a1e",
)
PLACEMENT = "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7"
STOCK = "ebd19afb495957175eedc994a3fa35a069d17d135a3f82c14df62ac16e88715a"
LIBS = {
    "src/libllama.so": "aa1e18b41a8f04ed396e885f24288965a8961e611261e173774e9f9cd538b74a",
    "ggml/src/libggml.so": "5395348a4bffef748be95e7657cbd25dd2ceaaa50f4f00e0f9d58dc742329c0c",
}
NAMES = ("pos15.f32", "pos16.f32")
need = stock.check
sha = stock.sha


def digest(b):
    return hashlib.sha256(b).hexdigest()


def receipt(path, expected):
    b = path.read_bytes()
    need(digest(b) == expected, f"receipt SHA {path.name}")
    return json.loads(b)


def select(window):
    caps = [window[k]["cap_max_bytes"] for k in ("memory", "canonical_memory")]
    reasons = set(window["reason"])
    need(window["model_bytes_read"] == 0 and window["r0_launch"] == "NOT_RUN", "C55 work")
    if window["status"] == "PASS_RESOURCE_WINDOW_ONLY" and not reasons and min(caps) >= 20 * GIB:
        return 20
    need(
        window["status"] == "NOT_ADMITTED"
        and reasons
        and reasons <= {"HOST_CAP_PLUS_RESERVE_UNAVAILABLE", "C55_CAP_UNAVAILABLE"}
        and 10 * GIB <= min(caps) < 20 * GIB,
        "no E20/E10 admission",
    )
    return 10


def window_authority(path, expected, envelope, now=None):
    w = receipt(path, expected)
    need(select(w) == envelope, "wrong campaign envelope")
    need(w["runner_sha256"] == sha(Q / "nvme_admission/window.py"), "C55 runner")
    need(w["protocol_sha256"] == sha(Q / "nvme_admission/protocolo.md"), "C55 source protocol")
    p = receipt(path.parent / "resource-policy.json", w["canonical_policy_sha256"])
    snap = stock.read(path.parent / "snapshot.json")
    need(stock.policy_api.derive_policy(snapshot=snap) == p, "C55 derivation")
    need(p["memory"] == w["canonical_memory"], "C55 canonical cap")
    samples = path.parent / "samples.jsonl"
    need(sha(samples) == w["window_sha256"], "C55 witness digest")
    rows = [json.loads(line) for line in samples.read_text().splitlines()]
    need(len(rows) == w["samples"] >= 61 and 60 <= w["span_s"] < 100, "C55 coverage")
    end = datetime.fromisoformat(rows[-1]["utc"])
    age = ((now or datetime.now(UTC)) - end).total_seconds()
    need(0 <= age < 55 * 60, "C55 older than 55 min")
    limits = stock.policy_api.freeze_protocol_resource_limits(
        p,
        cgroup_memory_max_bytes=envelope * GIB,
        start_mode="CAPACITY_ADMISSION_START",
        execution_class="FILE_PAGING",
    )
    stock.policy_api.validate_resource_protocol({"limits": {}, "resources": limits})
    return w, p, limits


def references(raw_parent, stock_raw):
    packed, gold, arms = historical.inputs(raw_parent)
    need(
        digest(packed[:68]) == PACK17 and struct.unpack_from("<i", packed, 64)[0] == 976,
        "IDs/teacher",
    )
    targets = tuple(gold[i * ROW : (i + 1) * ROW] for i in range(2))
    need(tuple(map(digest, targets)) == GOLD, "two gold rows")
    official = receipt(Q / "stock_numeric/physical-r1/receipt.json", STOCK)
    sample = stock_raw.read_bytes()
    need(
        len(sample) == 3 * ROW and digest(sample) == official["raw_sha256"]["candidate.logits.f32"],
        "stock rows",
    )
    stock_targets = tuple(sample[i * ROW : (i + 1) * ROW] for i in range(2))
    need(
        [digest(row) for row in stock_targets] == [r["sha256"] for r in official["rows"][:2]],
        "stock row alignment",
    )
    return packed[:68], targets, stock_targets, arms


def placed(w, path):
    meta = receipt(path, PLACEMENT)
    model = Path(meta["working_copy"])
    identity = stock.identity(model)
    need(
        meta["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and meta["source_sha256"] == meta["destination_direct_reread"]["sha256"] == stock.MODEL_SHA
        and model.is_file()
        and not model.is_symlink()
        and identity == tuple(w["selected_stat"])
        and identity[2] == stock.MODEL_SIZE
        and model.samefile(stock.MODEL),
        "GGUF placement or FD metadata",
    )
    return model, identity


def verify_build(build_dir, build_sha, synthetic, synthetic_sha, objects):
    b = receipt(build_dir / "receipt.json", build_sha)
    s = receipt(synthetic, synthetic_sha)
    driver = run_path(str(HERE.parent / "driver/run.py"))
    need(
        b["sources"] == driver["sources"]()
        and b["ik_commit"] == driver["front"]["PIN"]
        and b["ik_tree"] == driver["front"]["TREE"],
        "driver source/pin",
    )
    exe = build_dir / "ik-cpu-numeric"
    need(
        b["status"] == "PASS_IK_CPU_NUMERIC_BUILD"
        and b["binary"] == exe.name
        and sha(exe) == b["binary_sha256"],
        "binary/build",
    )
    need(
        s["status"] == "PASS_IK_CPU_NUMERIC_SYNTHETIC"
        and s["build_sha256"] == build_sha
        and s["binary_sha256"] == b["binary_sha256"]
        and s["same_rows"] is True,
        "synthetic proof",
    )
    need(b["libraries"] == LIBS, "CPU-only GGML/llama")
    for rel, code in LIBS.items():
        p = (objects / rel).resolve(strict=True)
        need(b["closure"][p.name] == {"file": str(p), "sha256": code}, "project closure")
    for k, row in b["closure"].items():
        need(
            not any(v in k.lower() for v in ("cuda", "vulkan", "hip", "nvidia", "rocm", "opencl")),
            "GPU dependency",
        )
        need(sha(row["file"]) == row["sha256"], "changed provider")
    return exe, b


def child_env(objects):
    return {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "8",
        "GGML_MOE_PREFETCH_AHEAD": "0",
        "HF_HUB_OFFLINE": "1",
        "LD_LIBRARY_PATH": os.pathsep.join(str((objects / k).resolve().parent) for k in LIBS),
    }
