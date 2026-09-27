#!/usr/bin/env python3
"""Seal the scoped C6 replay bridge without changing C5 evidence."""

import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess

from c5_compare_flash_replay import parse_source, finite_f32
from c5_compare import EvidenceError, ROOT, write_new

PATCH_SHA = "c4104706a123ea92fb47bfab9a1f95a4e6cf106d"
REPLAY_SHA = "4fc543a036ee833572c28f122a9430f92230b6c098c75fadbca1fb647b187b01"
OUT = ROOT / "results/c6-d1-local-summary02.json"
FILES = {
    "a32_off": ("c6-d1-replay-a32-off01.f32", 32, "c5-d3-replay-a32-normal01.f32"),
    "a32_on": ("c6-d1-replay-a32-on01.f32", 32, "c5-d3-replay-a32-normal01.f32"),
    "b32_on": ("c6-d1-replay-b32-on01.f32", 32, "c5-d3-replay-b32-normal01.f32"),
    "b64_off": ("c6-d1-replay-b64-off01.f32", 64, "c5-d3-replay-b64-normal01.f32"),
    "b64_on": ("c6-d1-replay-b64-on01.f32", 64, "c5-d3-replay-b64-ref01.f32"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name, n):
    path = ROOT / "results" / name
    data = path.read_bytes()
    if len(data) != n * 4096 * 4:
        raise EvidenceError(f"{name}: output count or dtype wrong")
    finite_f32(data, name)
    return data


def main():
    if OUT.exists():
        raise SystemExit("no-replace C6 local report exists")
    try:
        patch = subprocess.check_output(["git", "-C", str(ROOT / "backends/streaming-c6-attn-compat"),
                                         "rev-parse", "HEAD"], text=True).strip()
        clean = subprocess.check_output(["git", "-C", str(ROOT / "backends/streaming-c6-attn-compat"),
                                         "status", "--porcelain"], text=True).strip()
        if patch != PATCH_SHA or clean:
            raise EvidenceError("backend source identity or clean worktree changed")
        replay_bin = (ROOT / "tools/c6_flash_replay").read_bytes()
        if sha(replay_bin) != REPLAY_SHA:
            raise EvidenceError("C6 native replay binary changed")
        arms = {"A": parse_source("A", 32), "B": parse_source("B", 64)}
        data = {}
        for role, (name, n, c5name) in FILES.items():
            data[role] = load(name, n)
            if data[role] != load(c5name, n):
                raise EvidenceError(f"{role}: C5 native bridge mismatch")
        if data["a32_off"] != arms["A"]["flash"] or data["b64_off"] != arms["B"]["flash"]:
            raise EvidenceError("patched OFF differs from captured target Flash output")
        if data["b64_on"][:32*4096*4] != data["a32_on"] or data["b32_on"] != data["a32_on"]:
            raise EvidenceError("compat ON did not recover shared 32 query outputs")
        fixture = ROOT / "results/c6-d1-fixture01.raw"
        fixture_equal = {}
        for off in sorted(fixture.glob("*-off.f32")):
            on = off.with_name(off.name.replace("-off.f32", "-on.f32"))
            a, b = off.read_bytes(), on.read_bytes()
            if len(a) == 0 or len(a) != len(b) or len(a) % 4:
                raise EvidenceError(f"{off.name}: fixture size mismatch")
            finite_f32(a, off.name)
            finite_f32(b, on.name)
            key = off.stem.removesuffix("-off")
            fixture_equal[key] = a == b
        expected = {
            "nq1-nkv256-f16": True, "nq1-nkv512-f16": True,
            "nq31-nkv256-f16": True, "nq32-nkv256-f16": True,
            "nq63-nkv256-f16": True, "nq64-nkv256-f16": False,
            "nq64-nkv256-f32": True, "nq65-nkv256-f16": False,
        }
        if fixture_equal != expected:
            raise EvidenceError("synthetic dispatch non-interference matrix changed")
        if (fixture / "missing-workspace.f32").exists() or (fixture / "invalid-mode.f32").exists():
            raise EvidenceError("negative case produced output")
        report = {"schema": "c6-d1-local-v1", "status": "DISPATCH_PATCH_QUALIFIED_LOCAL",
                  "patch_sha": patch, "replay_binary_sha256": REPLAY_SHA,
                  "replays_sha256": {k: sha(v) for k,v in data.items()},
                  "first32_b64_on_equals_a32": True,
                  "fixture_bitwise_equal_on_off": fixture_equal,
                  "negative_cases": ["mode=0 abort before output", "source missing", "source truncated",
                                     "source nonfinite", "output no-replace", "workspace absent abort before output"],
                  "scope": "native CPU Flash; captured layer0 inputs plus model-free dispatch fixtures"}
    except (EvidenceError, OSError, ValueError, TypeError, KeyError) as exc:
        report = {"schema": "c6-d1-local-v1", "status": "FAIL_EVIDENCE", "reason": str(exc)}
    write_new(OUT, report)
    print(json.dumps({"status": report["status"], "reason": report.get("reason")}))
    return 0 if report["status"] == "DISPATCH_PATCH_QUALIFIED_LOCAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
