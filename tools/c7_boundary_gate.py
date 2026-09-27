#!/usr/bin/env python3
"""Validate C7 P12 capture completeness and same-profile full logits."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources

VOCAB = 201088
ROW_BYTES = VOCAB * 4
PHASES = ("prefill0", "prefill128", "prefill_final", "decode0", "decode1", "decode7", "decode31")
LOGIT_PHASES = ("prefill_final", "decode0", "decode1", "decode7", "decode31")
# The graph's biased router logits and probs are the same tensor. Its later
# callback name is ffn_moe_probs, so the earlier alias is not observable here.
CORE = {"attn_post_norm", "ffn_moe_logits", "ffn_moe_probs",
        "ffn_moe_topk", "ffn_moe_weights_softmax", "ffn_moe_out"}
OPTIONAL = {"ffn_moe_topk_stream", "ffn_moe_wave_ids", "ffn_moe_wave_mask",
            "ffn_moe_gate_biased", "ffn_moe_up_biased", "ffn_moe_down_biased",
            "ffn_moe_argsort"}
INDEX_FIELDS = ["phase", "layer", "chunk", "first_abs", "state_tokens", "name",
                "type", "ne", "nb", "bytes", "file"]
MASKED = [
    {"phase": "prefill0", "layer": "35", "chunk": "0", "first_abs": "0",
     "state_tokens": "0", "state": "N/A_MASKED", "reason": "output-mask-zero-rows"},
    {"phase": "prefill128", "layer": "35", "chunk": "4", "first_abs": "128",
     "state_tokens": "0", "state": "N/A_MASKED", "reason": "output-mask-zero-rows"},
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path, header):
    with path.open() as source:
        reader = csv.DictReader(source, delimiter="\t")
        if reader.fieldnames != header:
            raise GateError("index header changed: " + str(path))
        return list(reader)


def f32(data, count):
    if len(data) != count * 4 or any(not math.isfinite(x) for (x,) in struct.iter_unpack("<f", data)):
        raise GateError("F32 payload size/nonfinite")
    return data


def logical_values(data, ne, nb, dtype):
    for i3 in range(ne[3]):
        for i2 in range(ne[2]):
            for i1 in range(ne[1]):
                for i0 in range(ne[0]):
                    offset = i0*nb[0] + i1*nb[1] + i2*nb[2] + i3*nb[3]
                    if dtype == "f32":
                        if not math.isfinite(struct.unpack_from("<f", data, offset)[0]):
                            raise GateError("nonfinite logical capture value")
                    elif struct.unpack_from("<i", data, offset)[0] < 0:
                        raise GateError("negative routed ID")


def source(stem, variant, binary, input_sha):
    manifest_path = Path(str(stem) + ".json")
    manifest = strict_json(manifest_path.read_text())
    n_samples = resources(manifest, Path(str(stem) + ".samples.jsonl"))
    if manifest["run_id"] != stem.name or manifest["variant"] != variant or \
       manifest["workload_sha256"] != input_sha or manifest["command"][0] != binary or \
       manifest["explicit_env"] != {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"} or \
       manifest["artifact_identity"]["stat_at_launch"] != manifest["artifact_identity"]["stat_at_end"] or \
       manifest["mapped_backend_libraries_sha256"] != manifest["backend_libraries_sha256"] or \
       not manifest["mapped_libraries_match_ldd"]:
        raise GateError("run provenance or mapped library mismatch: " + str(stem))
    if manifest["binary_sha256"] != sha(Path(binary)):
        raise GateError("run binary differs from frozen executable")
    for suffix, digest in manifest["output_sha256"].items():
        if sha(Path(str(stem) + suffix)) != digest:
            raise GateError("monitored raw hash changed: " + suffix)
    log = Path(str(stem) + ".stderr").read_text()
    placed = {int(layer): dev for layer, dev in re.findall(
        r"load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)", log)}
    if set(placed) != set(range(37)) or any(placed[i] != ("CPU" if i < 25 else "CUDA0") for i in range(37)):
        raise GateError("loader placement differs from observed P12 map")
    if "MoE expert streaming uses O_DIRECT" not in log:
        raise GateError("O_DIRECT streaming not observed")
    return manifest, {"manifest_sha256": sha(manifest_path), "samples": n_samples}


def state_metadata(phase, layer):
    if phase == "prefill0":
        return 0, 0, 32
    if phase == "prefill128":
        return 4, 128, 32
    if phase == "prefill_final":
        return 5, 188 if layer == 35 else 160, 1 if layer == 35 else 29
    step = int(phase.removeprefix("decode"))
    return -1, 189 + step, 1


def capture(root):
    if (root / "phases.txt").read_text().splitlines() != list(PHASES):
        raise GateError("capture phase schedule differs from freeze")
    masked = rows(root / "masked.tsv", list(MASKED[0]))
    if masked != MASKED:
        raise GateError("masked entries incomplete/extra")
    index = rows(root / "index.tsv", INDEX_FIELDS)
    expected_states = {(phase, layer) for phase in PHASES for layer in range(36)
                       if not (layer == 35 and phase in ("prefill0", "prefill128"))}
    observed_core = {}
    files = set()
    total_bytes = 0
    for row in index:
        try:
            phase, layer, stage = row["phase"], int(row["layer"]), row["name"]
            ne = tuple(int(x) for x in row["ne"].split(","))
            nb = tuple(int(x) for x in row["nb"].split(","))
            chunk, first_abs, tokens, size = (int(row[k]) for k in
                ("chunk", "first_abs", "state_tokens", "bytes"))
        except (ValueError, TypeError) as exc:
            raise GateError("malformed capture index value") from exc
        if (phase, layer) not in expected_states or stage not in CORE | OPTIONAL or \
           (chunk, first_abs, tokens) != state_metadata(phase, layer) or \
           row["type"] not in ("f32", "i32") or len(ne) != 4 or len(nb) != 4 or \
           any(x <= 0 for x in ne) or any(x <= 0 for x in nb) or nb[0] != 4 or \
           size != 4 + sum((ne[i]-1)*nb[i] for i in range(4)) or size <= 0:
            raise GateError("capture state/schema/stride/byte count invalid")
        if stage in CORE:
            key = (phase, layer, stage)
            if key in observed_core:
                raise GateError("duplicate core stage")
            observed_core[key] = True
            if stage in ("attn_post_norm", "ffn_moe_out"):
                target = (2880, tokens, 1, 1)
            elif stage in ("ffn_moe_logits", "ffn_moe_probs"):
                target = (128, tokens, 1, 1)
            elif stage == "ffn_moe_topk":
                target = (4, tokens, 1, 1)
            else:
                target = (1, 4, tokens, 1)
            target_type = "i32" if stage == "ffn_moe_topk" else "f32"
            if ne != target or row["type"] != target_type:
                raise GateError("core stage dtype or shape invalid")
        file = row["file"]
        if not re.fullmatch(rf"{re.escape(phase)}_{layer}_{re.escape(stage)}_\d+\.bin", file) or file in files:
            raise GateError("duplicate/invalid capture file name")
        files.add(file)
        payload = (root / file).read_bytes()
        if len(payload) != size:
            raise GateError("capture payload differs from declared bytes")
        logical_values(payload, ne, nb, row["type"])
        total_bytes += size
    expected_core = {(phase, layer, stage) for phase, layer in expected_states for stage in CORE}
    if set(observed_core) != expected_core or total_bytes > 256*2**20:
        raise GateError("capture core state set incomplete/extra or volume exceeded")
    checked = rows(root / "byte_checks.tsv", ["phase", "layer", "wave", "logical", "slot",
                                                "generation", "tensor", "bytes", "status"])
    witness = {(int(row["layer"]), int(row["tensor"])) for row in checked if row["status"] == "EQUAL"}
    if not all((layer, kind) in witness for layer in (0, 25, 29, 35) for kind in range(6)):
        raise GateError("byte/lifetime witness incomplete")
    logits = {}
    for phase in LOGIT_PHASES:
        path = root / (phase + ".logits.f32")
        logits[phase] = f32(path.read_bytes(), VOCAB)
    control = {"index.tsv", "masked.tsv", "byte_checks.tsv", "route_prestate.tsv",
               "phases.txt", "stages.txt"} | {p + ".logits.f32" for p in LOGIT_PHASES}
    actual_files = {p.name for p in root.iterdir() if p.is_file()}
    if actual_files != files | control:
        raise GateError("capture has unindexed/absent files")
    return logits, {"numeric_states": len(expected_states), "masked_states": len(masked),
                    "index_rows": len(index), "capture_bytes": total_bytes,
                    "checked_slices": len(checked), "index_sha256": sha(root / "index.tsv"),
                    "masked_sha256": sha(root / "masked.tsv")}


def off(stem, numeric_ids):
    prompt, continuation = numeric_ids
    row_index = rows(Path(str(stem) + ".rows.tsv"), ["phase", "position", "row", "token_id"])
    expected = [{"phase": "prefill", "position": "188", "row": "0", "token_id": prompt[-1]}]
    expected.extend({"phase": "decode", "position": str(189+i), "row": str(i+1),
                     "token_id": continuation[i]} for i in range(32))
    if row_index != expected:
        raise GateError("OFF output masks/positions/IDs differ from freeze")
    data = f32(Path(str(stem) + ".f32").read_bytes(), 33*VOCAB)
    selected = dict(zip(LOGIT_PHASES, (0, 1, 2, 8, 32)))
    return {phase: data[row*ROW_BYTES:(row+1)*ROW_BYTES] for phase, row in selected.items()}, \
           {"all_rows_sha256": hashlib.sha256(data).hexdigest(),
            "rows_sha256": sha(Path(str(stem) + ".rows.tsv"))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("off1", type=Path)
    p.add_argument("on", type=Path)
    p.add_argument("off2", type=Path)
    p.add_argument("--capture-root", type=Path, required=True)
    p.add_argument("--ids", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        lines = [line.split("\t") for line in args.ids.read_text().splitlines()]
        selected = next(row for row in lines if row[0] == "log_medium")
        prompt, continuation = selected[1].split(","), selected[2].split(",")
        if len(prompt) != 189 or len(continuation) != 43:
            raise GateError("numeric input count changed")
        identity = []
        off_logits = []
        for stem, variant in ((args.off1, "P12-observer-off"),
                              (args.on, "P12-observer-on"),
                              (args.off2, "P12-observer-off-repeat")):
            binary = "tools/c7_boundary_capture" if stem == args.on else "tools/c7_profile_probe"
            identity.append(source(stem, variant, binary, sha(args.ids))[0])
            if stem != args.on:
                off_logits.append(off(stem, (prompt, continuation)))
        for key in ("model_id", "model_path", "backend_sha", "backend_libraries_sha256",
                    "mapped_backend_libraries_sha256", "workload_sha256"):
            if any(manifest[key] != identity[0][key] for manifest in identity[1:]):
                raise GateError("cross-run provenance mismatch: " + key)
        on_logits, coverage = capture(args.capture_root)
        mismatch = []
        for phase in LOGIT_PHASES:
            reference = off_logits[0][0][phase]
            for arm, candidate in (("on", on_logits[phase]), ("off2", off_logits[1][0][phase])):
                if reference != candidate:
                    first = next(i for i in range(VOCAB) if reference[4*i:4*i+4] != candidate[4*i:4*i+4])
                    mismatch.append({"arm": arm, "phase": phase, "first_logit_index": first})
        status = "SAME_PROFILE_PASS" if not mismatch else "FAIL_SAME_PROFILE_FIDELITY"
        result = {"schema": "c7-p12-boundary-gate-v1", "status": status,
                  "mismatch": mismatch, "coverage": coverage,
                  "logits_sha256": {"off1": off_logits[0][1], "off2": off_logits[1][1],
                                    "on": {k: hashlib.sha256(v).hexdigest() for k, v in on_logits.items()}},
                  "raw_manifest_sha256": {m["run_id"]: sha(Path(str(stem)+".json")) for m, stem in
                                           zip(identity, (args.off1, args.on, args.off2))}}
    except (OSError, ValueError, KeyError, IndexError, TypeError, GateError) as exc:
        result = {"schema": "c7-p12-boundary-gate-v1", "status": "FAIL_RESOURCES_OR_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as target:
        json.dump(result, target, indent=2, sort_keys=True, allow_nan=False)
        target.write("\n")
    print(json.dumps({"status": result["status"], "reason": result.get("reason"),
                      "mismatch": result.get("mismatch")}))
    return 0 if result["status"] == "SAME_PROFILE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
