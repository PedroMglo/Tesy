#!/usr/bin/env python3
"""Seal the C6 113-ID model and GPU Flash diagnostic with strict identities."""

import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c5_compare import EvidenceError, IDS, IDS_SHA, MODEL, MODEL_SHA, ROOT, VOCAB, write_new

OUT = ROOT / "results/c6-d2-short-diagnostic-summary03.json"
PIN = "1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5"
PATCH = "c4104706a123ea92fb47bfab9a1f95a4e6cf106d"
ROWS = "case\trow\ttokens\nlatency-short\t0\t113\n"
SPECS = {
    "A0": ("c6-d2-a0-original32-short01", "streaming", PIN, "tools/c4_prefill_probe", "37357baa6b822dacdfb8182b778ee0d27b2737ede5419d7c3b0eb3d826990964", 32, False),
    "A": ("c6-d2-a-patched32-off-short01", "streaming-c6-attn-compat", PATCH, "tools/c6_prefill_probe_ub32", "ac3e5b97c3fd1daa537bec7e640ee62595ce7b82336815b10af68e925d574986", 32, False),
    "Aplus": ("c6-d2-aplus-patched32-on-short01", "streaming-c6-attn-compat", PATCH, "tools/c6_prefill_probe_ub32", "ac3e5b97c3fd1daa537bec7e640ee62595ce7b82336815b10af68e925d574986", 32, True),
    "B": ("c6-d2-b-patched64-off-short01", "streaming-c6-attn-compat", PATCH, "tools/c6_prefill_probe_ub64", "846201add96d67dd03e09bc3eb8f75080d0cb9966c3327a662bb9734c30774b2", 64, False),
    "C1": ("c6-d2-c1-patched64-on-short01", "streaming-c6-attn-compat", PATCH, "tools/c6_prefill_probe_ub64", "846201add96d67dd03e09bc3eb8f75080d0cb9966c3327a662bb9734c30774b2", 64, True),
    "C2": ("c6-d2-c2-patched64-on-short01", "streaming-c6-attn-compat", PATCH, "tools/c6_prefill_probe_ub64", "846201add96d67dd03e09bc3eb8f75080d0cb9966c3327a662bb9734c30774b2", 64, True),
}
CAPTURES = {
    "attn0_A": ("c6-d2diag-attn-aplus32-on01", "693647e563f9fd0b511970946a1ba91eafd4c43788f197cbfeb0ce57377551d4", 32, "Aplus"),
    "attn0_C": ("c6-d2diag-attn-c64-on01", "693647e563f9fd0b511970946a1ba91eafd4c43788f197cbfeb0ce57377551d4", 64, "C1"),
    "layer_A": ("c6-d2diag-layer-aplus32-on01", "b5445003f07fbc35a0f8703b8b37b716c2c0bb03e8f7d5127164d843a3144c4a", 32, "Aplus"),
    "layer_C": ("c6-d2diag-layer-c64-on01", "b5445003f07fbc35a0f8703b8b37b716c2c0bb03e8f7d5127164d843a3144c4a", 64, "C1"),
    "gpuop_A": ("c6-d2diag-gpu29-aplus32-on01", "b5563bb31a5f1ecc14fd53d10690ad19cf6f7cdb9b8bc506047ee169afe5c53f", 32, "Aplus"),
    "gpuop_C": ("c6-d2diag-gpu29-c64-on01", "b5563bb31a5f1ecc14fd53d10690ad19cf6f7cdb9b8bc506047ee169afe5c53f", 64, "C1"),
    "gpuattn_A": ("c6-d2diag-gpu29attn-aplus32-on01", "a01fad4b03b7c0ab555c28e9707a1d5edf1ad41af90e89b71f099a34347bc350", 32, "Aplus"),
    "gpuattn_C": ("c6-d2diag-gpu29attn-c64-on01", "a01fad4b03b7c0ab555c28e9707a1d5edf1ad41af90e89b71f099a34347bc350", 64, "C1"),
    "gpusrc_A": ("c6-d2diag-gpu29src-aplus32-on01", "14060733e812dc25b627abb10fbdd7e1eea6701bd4d987b3c3b515527aa7281d", 32, "Aplus"),
    "gpusrc_C": ("c6-d2diag-gpu29src-c64-on01", "14060733e812dc25b627abb10fbdd7e1eea6701bd4d987b3c3b515527aa7281d", 64, "C1"),
}
REPLAYS = {
    "A32": "c6-d2diag-gpu29-replay-a32-01",
    "C64": "c6-d2diag-gpu29-replay-c64-01",
    "C32second": "c6-d2diag-gpu29-replay-c32second-01",
}
REPLAY_BIN = "3eabe6607fea2804d7ae766593adeca9fe0281fb4cc21416d94961e3aa83480b"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(path.read_bytes())


def read_f32(path, n):
    data = path.read_bytes()
    if len(data) != n * 4 or any(not math.isfinite(x[0]) for x in struct.iter_unpack("<f", data)):
        raise EvidenceError(f"bad f32 count/nonfinite: {path}")
    return data


def manifest(stem, backend, revision, binary, bin_sha, ubatch, on, capture=False):
    p = ROOT / "results" / stem
    m = strict_json(Path(str(p)+".json").read_text())
    env = {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"}
    if on:
        env["TESY_CPU_FA_PREFILL_VEC_COMPAT"] = "1"
    if m.get("run_id") != stem or m.get("backend") != backend or m.get("backend_sha") != revision or \
       m.get("binary_sha256") != bin_sha or m.get("workload_sha256") != IDS_SHA or \
       m.get("model_path") != MODEL or m.get("artifact_identity", {}).get("sha256_previously_verified") != MODEL_SHA or \
       m.get("explicit_env") != env or m.get("limits", {}).get("require_telemetry") is not True:
        raise EvidenceError(f"{stem}: identity/environment mismatch")
    expected = [binary, MODEL, IDS, f"results/{stem}", "short"]
    if capture:
        expected += ["--ubatch", str(ubatch)]
    if m.get("command") != expected:
        raise EvidenceError(f"{stem}: effective command changed")
    if file_sha(ROOT / binary) != bin_sha:
        raise EvidenceError(f"{stem}: binary changed after run")
    resources(m, Path(str(p)+".samples.jsonl"))
    stderr = Path(str(p)+".stderr").read_text()
    if "offloaded 8/37 layers to GPU" not in stderr or "Flash Attention was auto, set to enabled" not in stderr:
        raise EvidenceError(f"{stem}: placement/Flash path missing")
    if Path(str(p)+".rows.tsv").read_text() != ROWS:
        raise EvidenceError(f"{stem}: output row/mask changed")
    data = read_f32(Path(str(p)+".f32"), VOCAB)
    for suffix, digest in m.get("output_sha256", {}).items():
        if file_sha(Path(str(p)+suffix)) != digest:
            raise EvidenceError(f"{stem}: monitored output changed")
    return m, data


def capture_rows(stem):
    root = ROOT / "results" / (stem + ".raw")
    index = root / "index.tsv"
    with index.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        header = ["chunk", "stage", "layer", "first_abs", "n_tokens", "type", "ne", "nb", "bytes", "file"]
        if reader.fieldnames != header:
            raise EvidenceError(f"{stem}: capture index schema changed")
        lines = list(reader)
    rows = {}
    digests = []
    for r in lines:
        if set(r) != set(header) or r["type"] != "f32":
            raise EvidenceError(f"{stem}: capture dtype/metadata changed")
        n, count, start, layer = (int(r[k]) for k in ("n_tokens", "bytes", "first_abs", "layer"))
        ne = tuple(int(v) for v in r["ne"].split(","))
        nb = tuple(int(v) for v in r["nb"].split(","))
        if n == 0:
            if count or r["file"] != "-":
                raise EvidenceError(f"{stem}: invalid empty output")
            continue
        if r["file"] != Path(r["file"]).name or n < 1 or start < 0 or start+n > 113 or \
           count % (n*4) or nb[0] != 4 or len(ne) != 4 or len(nb) != 4:
            raise EvidenceError(f"{stem}: capture shape/stride invalid")
        payload = (root / r["file"]).read_bytes()
        if len(payload) != count:
            raise EvidenceError(f"{stem}: capture file truncated")
        read_f32(root / r["file"], count//4)
        width = count//(n*4)
        digests.append((r["file"], sha(payload)))
        for i in range(n):
            key = (r["stage"], layer, start+i)
            if key in rows:
                raise EvidenceError(f"{stem}: duplicate logical capture state")
            rows[key] = payload[i*width*4:(i+1)*width*4]
    root_digest = sha("".join(f"{name}:{digest}\n" for name,digest in sorted(digests)).encode())
    return rows, {"index_sha256": file_sha(index), "raw_file_count": len(digests),
                  "raw_root_digest": root_digest}


def comparison(a, b, stage, layer, tokens):
    matched = 0
    first = None
    count = 0
    max_abs = 0.0
    for t in tokens:
        key = (stage, layer, t)
        if key not in a or key not in b or len(a[key]) != len(b[key]):
            raise EvidenceError(f"capture state missing/shape changed: {key}")
        left, right = a[key], b[key]
        if left == right:
            matched += 1
            continue
        for off in range(0, len(left), 4):
            if left[off:off+4] != right[off:off+4]:
                count += 1
                if first is None:
                    first = {"absolute_token": t, "feature": off//4}
                x = struct.unpack_from("<f", left, off)[0]
                y = struct.unpack_from("<f", right, off)[0]
                max_abs = max(max_abs, abs(x-y))
    return {"equal_rows": matched, "compared_rows": len(tuple(tokens)),
            "first_difference": first, "different_f32": count, "max_abs": max_abs}


def main():
    if OUT.exists():
        raise SystemExit("no-replace C6 D2 report exists")
    try:
        if file_sha(ROOT / IDS) != IDS_SHA:
            raise EvidenceError("exact 113-ID source hash changed")
        outputs, runs = {}, {}
        original_libs = patched_libs = None
        for role, spec in SPECS.items():
            name, backend, revision, binary, bin_sha, ubatch, on = spec
            m, payload = manifest(name, backend, revision, binary, bin_sha, ubatch, on)
            libs = m.get("backend_libraries_sha256")
            if not isinstance(libs, dict) or len(libs) < 5 or not any("libggml-cpu" in k for k in libs):
                raise EvidenceError(f"{name}: loaded library identity missing")
            if backend == "streaming":
                original_libs = libs
            elif patched_libs is None:
                patched_libs = libs
            elif libs != patched_libs:
                raise EvidenceError(f"{name}: patched libraries differ across arms")
            outputs[role] = payload
            runs[role] = {"manifest_sha256": file_sha(ROOT/"results"/(name+".json")),
                          "logits_sha256": sha(payload), "completion_s": float(Path(str(ROOT/"results"/name)+".cases.tsv").read_text().splitlines()[1].split("\t")[3]),
                          "maxima": m["maxima"]}
        if original_libs == patched_libs or \
           outputs["A0"] != outputs["A"] or outputs["A"] != outputs["Aplus"] or \
           outputs["B"] != read_f32(ROOT/"results/c5-d1-b1-ub64-short01.f32", VOCAB) or \
           outputs["C1"] != outputs["C2"] or outputs["B"] == outputs["A0"]:
            raise EvidenceError("original/OFF/within-form bridge failed")
        cap, seals = {}, {}
        for role, (name, bin_sha, ubatch, control) in CAPTURES.items():
            binary = "tools/" + ("c6_attention_capture_probe" if role.startswith("attn0") else
                                  "c6_layer_capture_probe" if role.startswith("layer") else
                                  "c6_gpu29_op_capture_probe" if role.startswith("gpuop") else
                                  "c6_gpu29_attention_capture_probe" if role.startswith("gpuattn") else
                                  "c6_gpu29_flash_src_probe")
            m, payload = manifest(name, "streaming-c6-attn-compat", PATCH, binary,
                                  bin_sha, ubatch, True, capture=True)
            if payload != outputs[control] or m["backend_libraries_sha256"] != patched_libs:
                raise EvidenceError(f"{name}: observer effect or libraries changed")
            cap[role], seals[role] = capture_rows(name)
        attn0 = {stage: comparison(cap["attn0_A"], cap["attn0_C"], stage, 0, range(113))
                 for stage in ("attn_norm", "Q_rope", "K_rope", "V_reshape", "flash_attn", "attn_out")}
        layers = {str(i): comparison(cap["layer_A"], cap["layer_C"], "l_out", i,
                                      [112] if i == 35 else range(113)) for i in range(36)}
        gpuop = {stage: comparison(cap["gpuop_A"], cap["gpuop_C"], stage, 29, range(113))
                 for stage in ("attn_norm", "attn_out", "ffn_inp", "attn_post_norm", "ffn_moe_out", "l_out")}
        gpuattn = {stage: comparison(cap["gpuattn_A"], cap["gpuattn_C"], stage, 29, range(113))
                   for stage in ("Q_proj", "Q_bias", "Q_reshape", "Q_rope", "K_proj", "K_bias",
                                 "K_reshape", "K_rope", "V_proj", "V_bias", "V_reshape",
                                 "flash_attn", "kqv_out", "attn_out")}
        raw_a = ROOT/"results/c6-d2diag-gpu29src-aplus32-on01.raw"
        raw_c = ROOT/"results/c6-d2diag-gpu29src-c64-on01.raw"
        source_indexes = {}
        for arm, root, n in (("A", raw_a, 32), ("C", raw_c, 64)):
            path = root/"flash_sources.tsv"
            with path.open() as f:
                reader = csv.DictReader(f, delimiter="\t")
                if reader.fieldnames != ["role", "name", "op", "type", "ne", "nb", "bytes", "file"]:
                    raise EvidenceError(f"{arm}: Flash source index schema changed")
                entries = list(reader)
            if [r["role"] for r in entries] != ["q", "k", "v", "mask", "sinks"]:
                raise EvidenceError(f"{arm}: Flash source role list changed/duplicated")
            expected = {
                "q": ("f32", (64,n,64,1), (4,16384,256,n*16384), n*4096*4),
                "k": ("f16", (64,256,8,1), (2,1024,128,4194304), 262144),
                "v": ("f16", (64,256,8,1), (2,1024,128,4194304), 262144),
                "mask": ("f16", (256,n,1,1), (2,512,n*512,n*512), n*256*2),
                "sinks": ("f32", (64,1,1,1), (4,256,256,256), 256),
            }
            for row in entries:
                role = row["role"]
                dtype, ne, nb, byte_count = expected[role]
                if row["type"] != dtype or tuple(int(v) for v in row["ne"].split(",")) != ne or \
                   tuple(int(v) for v in row["nb"].split(",")) != nb or int(row["bytes"]) != byte_count or \
                   row["file"] != f"flash_src_{role}.bin" or row["op"] != ("NONE" if role in ("mask","sinks") else "PERMUTE") or \
                   len((root/row["file"]).read_bytes()) != byte_count:
                    raise EvidenceError(f"{arm}: {role} Flash source layout/bytes changed")
            source_indexes[arm] = {"sha256": file_sha(path), "roles": [r["role"] for r in entries]}
        sources = {}
        for role in ("q", "k", "v", "mask", "sinks"):
            a = (raw_a/f"flash_src_{role}.bin").read_bytes()
            c = (raw_c/f"flash_src_{role}.bin").read_bytes()
            row = 16384 if role == "q" else 512 if role == "mask" else 0
            equal = a == c[32*row:64*row] if row else a == c
            sources[role] = {"A_sha256": sha(a), "C_sha256": sha(c), "common_input_equal": equal}
        if not all(v["common_input_equal"] for v in sources.values()):
            raise EvidenceError("GPU Flash common-source alignment failed")
        replay = {}
        for role, name in REPLAYS.items():
            p = ROOT/"results"/name
            m = strict_json(Path(str(p)+".json").read_text())
            if m.get("returncode") != 0 or m.get("stop_reason") is not None or \
               m.get("backend_sha") != PATCH or m.get("binary_sha256") != REPLAY_BIN or \
               m.get("command") != ["tools/c6_gpu29_flash_replay", role, "normal", f"results/{name}.f32"] or \
               m.get("cgroup_start", {}).get("memory_max") != 18*2**30 or \
               m.get("cgroup_end", {}).get("swap_current") != 0:
                raise EvidenceError(f"{name}: native replay identity/resource failure")
            replay[role] = read_f32(Path(str(p)+".f32"), (64 if role=="C64" else 32)*4096)
        captured_a = (raw_a/"chunk1_flash_attn_29.f32").read_bytes()
        captured_c = (raw_c/"chunk0_flash_attn_29.f32").read_bytes()
        if replay["A32"] != captured_a or replay["C64"] != captured_c or \
           replay["C32second"] != replay["A32"] or replay["C64"][32*4096*4:] == replay["A32"]:
            raise EvidenceError("native GPU same-form or shape-intervention bridge failed")
        a, c = outputs["Aplus"], outputs["C1"]
        different = [i for i in range(VOCAB) if a[4*i:4*i+4] != c[4*i:4*i+4]]
        av = struct.unpack(f"<{VOCAB}f", a); cv = struct.unpack(f"<{VOCAB}f", c)
        delta = [y-x for x,y in zip(av,cv)]
        report = {"schema": "c6-d2-short-diagnostic-v1", "status": "COMPAT_NOT_RECOVERED_NEXT_DIVERGENCE",
                  "runs": runs, "capture_seals_post_run": seals,
                  "bridges": {"A0_eq_A_eq_Aplus": True, "B_eq_C5_B0": True, "C1_eq_C2": True},
                  "final_logits": {"n_vocab": VOCAB, "different_f32_bitwise": len(different),
                                   "max_abs": max(abs(x) for x in delta),
                                   "rmse": math.sqrt(sum(x*x for x in delta)/VOCAB),
                                   "Aplus_sha256": sha(a), "C_sha256": sha(c)},
                  "cpu_layer0_attention": attn0, "layer_outputs": layers,
                  "gpu_layer29_ops": gpuop, "gpu_layer29_attention": gpuattn,
                  "gpu_flash_sources": sources,
                  "gpu_flash_source_indexes": source_indexes,
                  "native_gpu_replay": {"A32_sha256": sha(replay["A32"]),
                                        "C64_sha256": sha(replay["C64"]),
                                        "C32second_sha256": sha(replay["C32second"]),
                                        "same_form_bridges_bitwise": True,
                                        "same_common_input_shape32_equals_A32": True,
                                        "same_common_input_shape64_second32_differs": True},
                  "scope": "113 fixed IDs, one external b256 decode, layer29 GPU Flash first next difference at token48/feature64; no performance promotion"}
    except Exception as exc:
        report = {"schema": "c6-d2-short-diagnostic-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    write_new(OUT, report)
    print(json.dumps({"status": report["status"], "reason": report.get("reason")}))
    return 0 if report["status"] == "COMPAT_NOT_RECOVERED_NEXT_DIVERGENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
