"""Classify addressability of one C270 CUDA rank using only pinned sources and small dumps."""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "010d654d60199eb0503a7976d18d428ad01eb025f8a30d7ff8e7058b5e74ea99"
MANIFEST = "d79d180a18cf6c0f0767d02307904e679c0edd4fa10c12a3256b87a398dd8002"
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
TREE = "49812e6f011a8cf0fc14a71074e5f4b120f87216"
C270 = "1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6"
SET = "3402d411f6baf85cfe82067bf106730776939b4822317e11dee40b3a654d0029"
ARM = Path("tesy-c270-driver-20261125-r01")
CAP = ARM / "raw/tesy-c270-driver-20261125-r01.capture"
WIDTH, BLOCK, BQ, SLOTS = 2880, 32, 17, 40
ROLE = WIDTH * (WIDTH // BLOCK) * BQ
CUDA = "ggml/src/ggml-cuda/"
ANCHORS = {
    "ggml/src/ggml-common.h": [
        "#define QK_MXFP4 32",
        "sizeof(block_mxfp4) == sizeof(uint8_t) + QK_MXFP4/2",
    ],
    "src/llama-moe-stream.cpp": [
        "ggml_new_tensor_3d(ctx, meta->type, meta->ne[0], meta->ne[1], n_slots)",
        "ggml_nbytes(cache) == nb_expert * n_slots",
        "ggml_backend_tensor_set(wt.cache, data, (size_t) w.slot*wt.nb_expert, wt.nb_expert)",
    ],
    "src/llama-graph.cpp": [
        'cb(ids_gemm, "ffn_moe_topk_stream", il)',
        "build_lora_mm_id(up_exps, cur, ids_gemm",
        "ggml_add_id(ctx0, up, up_exps_b, logical_ids)",
        "build_lora_mm_id(gate_exps, cur, ids_gemm",
        "build_lora_mm_id(down_exps, cur, ids_gemm",
        "build_expert_gemms(cur, ids_gemm, selected_experts)",
    ],
    CUDA + "ggml-cuda.cu": [
        "info.devices[id].integrated = false",
        "size += ggml_row_size(tensor->type, MATRIX_ROW_PADDING - ne0 % MATRIX_ROW_PADDING)",
        "ffn_up_bias->src[2] != ffn_up->src[2]",
        "const int mmvq_mmid_max = get_mmvq_mmid_max_batch(src0->type, cc)",
        "if (ne2 <= mmvq_mmid_max)",
        "ggml_cuda_mul_mat_vec_q(ctx, src0, src1, ids, dst)",
        "integrated && ggml_backend_buft_is_cuda_host(buft)",
    ],
    CUDA + "common.cuh": ["#define MATRIX_ROW_PADDING 512"],
    CUDA + "mmvq.cu": [
        "cc >= GGML_CUDA_CC_ADA_LOVELACE",
        "return MMVQ_MAX_BATCH_SIZE;",
        "case GGML_TYPE_MXFP4:   return vec_dot_mxfp4_q8_1",
        "ncols_dst == 1 && ids ? ids[channel_dst]",
        "channel_x*stride_channel_x + row0*stride_row_x",
        "vx, &y[j*stride_col_y + kby], kbx_offset + i*stride_row_x + kbx",
        "vgate, &y[j*stride_col_y + kby], kbx_offset + i*stride_row_x + kbx",
        "src0->nb[2] / ts_src0",
        "src0->data, src0->type, src1_q8_1.get(), ids_d",
        "ne02, nchannels_y, nchannels_dst, s02",
    ],
}


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path, expected):
    need(not path.is_symlink() and path.is_file(), "missing/foreign file: " + path.name)
    data = path.read_bytes()
    need(digest(data) == expected, "digest: " + path.name)
    return data


def source(backend):
    def git(*argv):
        return subprocess.check_output(["git", "-C", str(backend), *argv], timeout=5)

    need(
        git("rev-parse", "HEAD", "HEAD^{tree}").decode().splitlines() == [PIN, TREE], "backend pin"
    )
    result = {}
    for name, anchors in ANCHORS.items():
        raw = git("show", PIN + ":" + name)
        need((backend / name).read_bytes() == raw, "source changed: " + name)
        lines = raw.decode().splitlines()
        numbers = []
        for anchor in anchors:
            hits = [i for i, line in enumerate(lines, 1) if anchor in line]
            need(hits, "source anchor: " + anchor)
            numbers.append(hits[0])
        result[name] = {"sha256": digest(raw), "anchor_lines": numbers}
    return result


def capture(part):
    manifest = json.loads(read(part / "manifest.json", MANIFEST))["files"]

    def checked(name):
        record = manifest[str(name)]
        raw = read(part / name, record["sha256"])
        need(len(raw) == record["bytes"], "size: " + str(name))
        return raw

    def tsv(name):
        raw = checked(CAP / name)
        return list(csv.DictReader(io.StringIO(raw.decode()), delimiter="\t"))

    rec = checked(ARM / "receipt.json")
    need(
        digest(rec) == C270 and json.loads(rec)["status"] == "PASS_SELECTED_C269_BRIDGE",
        "physical C270",
    )
    protocol = json.loads(checked(ARM / "protocol.json"))
    need(
        protocol["pinned"]["backend_commit"] == PIN and protocol["pinned"]["backend_tree"] == TREE,
        "C270 build",
    )
    rows = [r for r in tsv("index.tsv") if r["phase"] == "decode0" and r["layer"] == "35"]
    outputs = {}
    values = {}
    for key, dims, dtype in (
        ("attn_post_norm", (2880, 1, 1, 1), "f32"),
        ("ffn_moe_topk", (4, 1, 1, 1), "i32"),
        ("ffn_moe_topk_stream", (4, 1, 1, 1), "i32"),
        ("ffn_moe_weights_softmax", (1, 4, 1, 1), "f32"),
        ("ffn_moe_out", (2880, 1, 1, 1), "f32"),
    ):
        (r,) = [v for v in rows if v["name"] == key]
        need(
            r["state_tokens"] == "1"
            and r["first_abs"] == "189"
            and r["chunk"] == "-1"
            and r["type"] == dtype
            and tuple(map(int, r["ne"].split(","))) == dims
            and Path(r["file"]).name == r["file"],
            "capture view: " + key,
        )
        data = checked(CAP / r["file"])
        count = math.prod(dims)
        need(len(data) == int(r["bytes"]) == 4 * count, "capture size")
        value = struct.unpack("<" + str(count) + ("f" if dtype == "f32" else "i"), data)
        need(all(map(math.isfinite, value)), "nonfinite: " + key)
        if count == 4:
            values[key] = value
        outputs[key] = {"sha256": digest(data), "elements": count, "type": dtype}
    ids, slots = values["ffn_moe_topk"], values["ffn_moe_topk_stream"]
    need(
        len(set(ids)) == len(set(slots)) == 4
        and all(0 <= i < 128 for i in ids)
        and all(0 <= s < SLOTS for s in slots),
        "rank/slot identity",
    )
    weights = values["ffn_moe_weights_softmax"]
    need(all(v > 0 for v in weights) and abs(sum(weights) - 1) < 1e-5, "mixture weights")
    raw = [r for r in tsv("byte_checks.tsv") if r["phase"] == "decode0" and r["layer"] == "35"]
    need(len(raw) == 24, "CUDA35 component census")
    bindings = []
    for i, s in zip(ids, slots, strict=True):
        matches = [r for r in raw if int(r["logical"]) == i and int(r["slot"]) == s]
        phases = {(int(r["tensor"]), int(r["bytes"])) for r in matches}
        gens = {int(r["generation"]) for r in matches}
        need(
            len(matches) == 6
            and phases == {(k, ROLE if k < 3 else WIDTH * 4) for k in range(6)}
            and all(r["wave"] == "0" and r["status"] == "EQUAL" for r in matches)
            and len(gens) == 1
            and min(gens) > 0,
            "binding/component/generation",
        )
        bindings.append([i, s, gens.pop()])
    pre = [r for r in tsv("route_prestate.tsv") if r["phase"] == "decode0" and r["layer"] == "35"]
    need(not pre, "new coldness observation: reconsider the protocol")
    return outputs, bindings


def single_base(slots, starts, stride):
    """Complete affine interval test; unit block offsets agree iff the starts agree."""
    need(
        len(slots) == len(starts)
        and len(slots) == len(set(slots))
        and all(0 <= s < SLOTS for s in slots)
        and stride >= ROLE
        and stride % BQ == 0,
        "invalid rank/stride",
    )
    return len({a - s * stride for s, a in zip(slots, starts, strict=True)}) == 1


def pages(slot, step, origin):
    """Pages covering the whole role, using the actual residue of the tensor origin."""
    start = origin + slot * ROLE
    stop = start + ROLE
    return start % step, (-stop) % step


def tagged_interval(ref, length):
    """Return the backing interval only if owner, generation and byte coverage agree."""
    slot, required_generation, resident_generation, start, end = ref
    need(0 <= slot < SLOTS and required_generation == resident_generation > 0, "stale generation")
    need(start >= 0 and length >= ROLE and start + ROLE <= end, "short backing interval")
    return (start, start + ROLE)


def remap_proof(bindings):
    slots = [b[1] for b in bindings]
    cold, gen = bindings[0][1:]

    # Abstract VAs are disjoint for staging and primary. The incompatibility is independent
    # of their absolute values given even one fixed resident rank and a distinct cold address.
    gpu, host = 2**35, 2**39
    wins = []
    for offset in (0, ROLE, 2 * ROLE):
        resident = [gpu + offset * SLOTS + s * ROLE for s in slots]
        intervals = [tagged_interval((cold, gen, gen, host + offset, host + 3 * ROLE), ROLE)]
        for (_, slot, generation), start in zip(bindings[1:], resident[1:], strict=True):
            intervals.append(
                tagged_interval((slot, generation, generation, start, start + ROLE), ROLE)
            )
        new = [start for start, _ in intervals]
        need(
            single_base(slots, resident, ROLE) and not single_base(slots, new, ROLE),
            "affine-address control",
        )
        wins.append(
            {
                "original_affine": True,
                "one_host_three_retained_affine": False,
                "separate_tagged_addresses_cover_exact_role_bytes": True,
            }
        )
    remaps = []
    for step in (4096, 65536):
        # A single role exactly spanning whole pages requires ROLE % step == 0 independent of
        # which side(s) adjoin other live slots or what residue the original arena VA has.
        gran = math.lcm(step, BQ)
        padded = ((ROLE + gran - 1) // gran) * gran
        need(
            ROLE % step
            and padded % BQ == padded % step == 0
            and all(pages(s, step, 0) != (0, 0) for s in range(SLOTS)),
            "granularity control",
        )
        before, after = pages(slots[0], step, 0)
        remaps.append(
            dict(
                page_bytes=step,
                cold_spill_before_if_aligned_base=before,
                cold_spill_after_if_aligned_base=after,
                both_dense_slot_edges_can_be_page_aligned=False,
                first_and_last_slots_depend_on_outer_padding=True,
                padded_channel_stride_example=padded,
                extra_arena_span_three_roles_40_slots_bytes=3 * SLOTS * (padded - ROLE),
                packed_role_start_residues=[(i * ROLE) % step for i in range(3)],
            )
        )
    return {
        "role_bytes": ROLE,
        "blocks_per_role": ROLE // BQ,
        "role_results": wins,
        "pages": remaps,
        "quant_tail_padding_per_dense_tensor_bytes": ((-WIDTH) % 512) // BLOCK * BQ,
    }


def run(part, backend):
    read(HERE / "protocol.md", PROTOCOL)
    sources = source(backend)
    views, bindings = capture(part)
    family = json.loads(
        read(HERE.parents[1] / "phase_fd/integrated/t1_set_floor/evidence/receipt.json", SET)
    )
    sets = family["conservation"]["by_phase_tier"]["decode_cuda"]
    return dict(
        status="NO_GO_SINGLE_BASE_ONE_HOST_RANK",
        scope="SOURCE_AND_FORMAL_ADDRESS_ONLY",
        protocol_sha256=PROTOCOL,
        source_sha256=digest(Path(__file__).read_bytes()),
        c270_sha256=C270,
        private_manifest_sha256=MANIFEST,
        source_tree=TREE,
        sources=sources,
        views=views,
        bindings_expert_slot_generation=bindings,
        rank=0,
        prestate_cuda35="UNOBSERVED",
        individual_contribution="NOT_CAPTURED",
        address=remap_proof(bindings),
        historical_t2_pre_final_decode_cuda={
            k: sets[k] for k in ("jobs", "set_events", "set_payload_bytes", "set_worker_ns")
        },
        set_receipt_sha256=SET,
        physical_kernel_trace="NOT_RUN",
        gpu_launches=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("part23", "backend", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = run(a.part23, a.backend)
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
