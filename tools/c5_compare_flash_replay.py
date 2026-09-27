#!/usr/bin/env python3
"""Seal C5 native Flash Attention source, bridge and path-intervention evidence."""

import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c5_compare import EvidenceError, IDS, IDS_SHA, MODEL, MODEL_SHA, BACKEND_SHA, ROOT, VOCAB, write_new
from c5_compare_layers import sha

BIN_SHA = "91e8dbad675e939053f49477f78e35ac5cc5bc081448dd1b90a6821116dee735"
REPLAY_BIN_SHA = "64c47f3b7ff9b7917d79f63a2a65b37ee84b6238cc70be0def9b9c28a51893e8"
OUT = ROOT / "results/c5-d3-native-replay-summary01.json"
STEMS = {"A": ROOT / "results/c5-d3-src-a-ub32-01",
         "B": ROOT / "results/c5-d3-src-b-ub64-01"}
CONTROLS = {"A": ROOT / "results/c5-d1-a1-ub32-short01",
            "B": ROOT / "results/c5-d1-b1-ub64-short01"}
ROLES = ("q", "k", "v", "mask", "sinks")
HEADER = ["role", "name", "op", "type", "ne", "nb", "bytes", "file"]
REPLAY_FILES = {
    "A32_normal": ("c5-d3-replay-a32-normal01.f32", 32),
    "B64_normal": ("c5-d3-replay-b64-normal01.f32", 64),
    "B32_normal": ("c5-d3-replay-b32-normal01.f32", 32),
    "B64_ref": ("c5-d3-replay-b64-ref01.f32", 64),
    "A32_ref": ("c5-d3-replay-a32-ref01.f32", 32),
}


def finite_f32(data, label):
    if len(data) % 4 or any(not math.isfinite(x[0]) for x in struct.iter_unpack("<f", data)):
        raise EvidenceError(f"{label}: nonfinite/truncated f32")


def finite_f16(data, label):
    if len(data) % 2 or any(not math.isfinite(x[0]) for x in struct.iter_unpack("<e", data)):
        raise EvidenceError(f"{label}: nonfinite/truncated f16")


def parse_source(arm, n):
    stem = STEMS[arm]
    manifest = strict_json(Path(str(stem)+".json").read_text())
    cmd = ["tools/c5_flash_src_probe", MODEL, IDS,
           str(stem.relative_to(ROOT)), "short", "--ubatch", str(n)]
    if manifest.get("run_id") != stem.name or manifest.get("backend_sha") != BACKEND_SHA or \
       manifest.get("model_path") != MODEL or \
       manifest.get("artifact_identity", {}).get("sha256_previously_verified") != MODEL_SHA or \
       manifest.get("workload_sha256") != IDS_SHA or manifest.get("binary_sha256") != BIN_SHA or \
       manifest.get("explicit_env") != {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"} or \
       manifest.get("command") != cmd:
        raise EvidenceError(f"{arm}: source observer provenance mismatch")
    resources(manifest, Path(str(stem)+".samples.jsonl"))
    stderr = Path(str(stem)+".stderr").read_text()
    if "offloaded 8/37 layers to GPU" not in stderr or \
       "Flash Attention was auto, set to enabled" not in stderr:
        raise EvidenceError(f"{arm}: placement/Flash Attention path absent")
    if Path(str(stem)+".rows.tsv").read_text() != "case\trow\ttokens\nlatency-short\t0\t113\n":
        raise EvidenceError(f"{arm}: requested output selection changed")
    final = Path(str(stem)+".f32").read_bytes()
    control = Path(str(CONTROLS[arm])+".f32").read_bytes()
    if len(final) != VOCAB*4 or len(control) != VOCAB*4 or final != control:
        raise EvidenceError(f"{arm}: observer changed final logits")
    raw = Path(str(stem)+".raw")
    with (raw/"flash_sources.tsv").open() as source:
        reader = csv.DictReader(source, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise EvidenceError(f"{arm}: source index schema changed")
        rows = list(reader)
    if tuple(row["role"] for row in rows) != ROLES:
        raise EvidenceError(f"{arm}: source roles changed or duplicated")
    expected = {
        "q": ("f32", (64,n,64,1), (4,16384,256,n*16384), n*4096*4),
        "k": ("f16", (64,256,8,1), (2,1024,128,4194304), 64*8*256*2),
        "v": ("f16", (64,256,8,1), (2,1024,128,4194304), 64*8*256*2),
        "mask": ("f16", (256,n,1,1), (2,512,n*512,n*512), n*256*2),
        "sinks": ("f32", (64,1,1,1), (4,256,256,256), 256),
    }
    data = {}
    hashes = {}
    for row in rows:
        role = row["role"]
        dtype, ne, nb, size = expected[role]
        try:
            recorded_ne = tuple(int(x) for x in row["ne"].split(","))
            recorded_nb = tuple(int(x) for x in row["nb"].split(","))
            recorded_size = int(row["bytes"])
        except (ValueError, TypeError) as exc:
            raise EvidenceError(f"{arm}: malformed source shape/stride") from exc
        if row["type"] != dtype or recorded_ne != ne or recorded_nb != nb or \
           recorded_size != size or row["file"] != f"flash_src_{role}.bin":
            raise EvidenceError(f"{arm}: {role} native source layout changed")
        payload = (raw/row["file"]).read_bytes()
        if len(payload) != size:
            raise EvidenceError(f"{arm}: {role} truncated source bytes")
        data[role] = payload
        hashes[role] = hashlib.sha256(payload).hexdigest()
    finite_f32(data["q"], f"{arm} Q")
    finite_f32(data["sinks"], f"{arm} sinks")
    for role in ("k", "v"):
        finite_f16(visible_kv(data[role], n), f"{arm} visible {role}")
    # The SWA cache has 256 cells. Query q may see only keys <=q.
    mask = data["mask"]
    for query in range(n):
        for key in range(256):
            value = struct.unpack_from("<e", mask, 2*(query*256+key))[0]
            if value != (0.0 if key <= query else -math.inf):
                raise EvidenceError(f"{arm}: mask differs at query/key {query}/{key}")
    # First chunk's logical operator output is required for the native bridge.
    with (raw/"index.tsv").open() as source:
        captures = list(csv.DictReader(source, delimiter="\t"))
    matches = [row for row in captures if row["chunk"] == "0" and
               row["stage"] == "flash_attn" and row["layer"] == "0"]
    if len(matches) != 1 or matches[0]["n_tokens"] != str(n) or \
       matches[0]["ne"] != f"64,64,{n},1" or matches[0]["type"] != "f32":
        raise EvidenceError(f"{arm}: first Flash output missing/shape changed")
    flash = (raw/matches[0]["file"]).read_bytes()
    if len(flash) != n*4096*4:
        raise EvidenceError(f"{arm}: first Flash output truncated")
    finite_f32(flash, f"{arm} Flash output")
    return {"manifest_sha256": sha(str(stem)+".json"),
            "source_index_sha256": sha(raw/"flash_sources.tsv"),
            "native_input_sha256": hashes,
            "final_logits_sha256": hashlib.sha256(final).hexdigest(),
            "flash_output_sha256": hashlib.sha256(flash).hexdigest(),
            "data": data, "flash": flash}


def visible_kv(raw, n):
    return b"".join(raw[key*1024+head*128:key*1024+head*128+128]
                    for key in range(n) for head in range(8))


def diff(a,b,width):
    if len(a) != len(b) or len(a) != 32*width*4:
        raise EvidenceError("replay comparison shape mismatch")
    if a == b:
        return {"bitwise_equal": True, "sha256": hashlib.sha256(a).hexdigest()}
    first = next(i//4 for i in range(0,len(a),4) if a[i:i+4] != b[i:i+4])
    delta = [y[0]-x[0] for x,y in zip(struct.iter_unpack("<f",a),
                                      struct.iter_unpack("<f",b))]
    return {"bitwise_equal": False, "first_abs_token": first//width,
            "first_feature": first%width,
            "different_float_count": sum(x!=0 for x in delta),
            "max_abs": max(abs(x) for x in delta),
            "rmse": math.sqrt(sum(x*x for x in delta)/len(delta)),
            "left_sha256": hashlib.sha256(a).hexdigest(),
            "right_sha256": hashlib.sha256(b).hexdigest()}


def main():
    if OUT.exists():
        raise SystemExit("no-replace report exists")
    try:
        if sha(ROOT/"tools/c5_flash_replay") != REPLAY_BIN_SHA:
            raise EvidenceError("native replay binary changed")
        arms = {"A": parse_source("A",32), "B": parse_source("B",64)}
        a,b = arms["A"]["data"], arms["B"]["data"]
        inputs = {"q_first32_equal": a["q"] == b["q"][:32*4096*4],
                  "k_first32_equal": visible_kv(a["k"],32) == visible_kv(b["k"],32),
                  "v_first32_equal": visible_kv(a["v"],32) == visible_kv(b["v"],32),
                  "mask_first32_equal": a["mask"] == b["mask"][:32*256*2],
                  "sinks_equal": a["sinks"] == b["sinks"]}
        if not all(inputs.values()):
            raise EvidenceError("native first32 semantic inputs unequal")
        replay = {}
        for name, (filename, n) in REPLAY_FILES.items():
            payload = (ROOT/"results"/filename).read_bytes()
            if len(payload) != n*4096*4:
                raise EvidenceError(f"{name}: replay output truncated")
            finite_f32(payload, name)
            replay[name] = payload
        if replay["A32_normal"] != arms["A"]["flash"] or \
           replay["B64_normal"] != arms["B"]["flash"]:
            raise EvidenceError("native direct same-form bridge not bitwise")
        first32 = {name: payload[:32*4096*4] for name,payload in replay.items()}
        comparisons = {
            "A32_normal_vs_B32_normal": diff(first32["A32_normal"], first32["B32_normal"],4096),
            "A32_normal_vs_A32_ref": diff(first32["A32_normal"], first32["A32_ref"],4096),
            "A32_normal_vs_B64_normal": diff(first32["A32_normal"], first32["B64_normal"],4096),
            "A32_normal_vs_B64_ref": diff(first32["A32_normal"], first32["B64_ref"],4096),
            "B64_normal_vs_B64_ref": diff(first32["B64_normal"], first32["B64_ref"],4096),
        }
        expected_equal = ("A32_normal_vs_B32_normal", "A32_normal_vs_A32_ref",
                          "A32_normal_vs_B64_ref")
        if any(not comparisons[k]["bitwise_equal"] for k in expected_equal) or \
           comparisons["A32_normal_vs_B64_normal"]["bitwise_equal"] or \
           comparisons["A32_normal_vs_B64_normal"]["first_abs_token"] != 0 or \
           comparisons["A32_normal_vs_B64_normal"]["first_feature"] != 0:
            raise EvidenceError("native grouping/reference-path intervention gate failed")
        report = {"schema": "c5-d3-native-replay-v1",
                  "status": "NATIVE_SHAPE_EFFECT_CAUSALLY_LOCALIZED",
                  "scope": "layer0 first internal chunk; 32 shared logical queries; pinned native CPU GGML Flash Attention",
                  "operator": "ggml_flash_attn_ext",
                  "source_dispatch": {"Q_tile": 64, "normal_32": "vec-only",
                                      "normal_64": "tiled", "ref_64": "vec-only forced"},
                  "same_form_native_bridge_bitwise": True,
                  "semantic_input_checks": inputs,
                  "comparisons": comparisons,
                  "arms": {name: {k:v for k,v in arm.items() if k not in ("data","flash")}
                           for name,arm in arms.items()},
                  "replay_outputs_sha256": {name:hashlib.sha256(payload).hexdigest()
                                            for name,payload in replay.items()},
                  "replay_binary_sha256": REPLAY_BIN_SHA,
                  "analyzer_sha256": sha(__file__),
                  "limits": "No ub64 promotion; FFN same-input differential not rerun because first divergence is before MoE"}
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        report = {"schema": "c5-d3-native-replay-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    write_new(OUT, report)
    print(json.dumps({"status": report["status"], "reason": report.get("reason")}))
    return 0 if report["status"] == "NATIVE_SHAPE_EFFECT_CAUSALLY_LOCALIZED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
