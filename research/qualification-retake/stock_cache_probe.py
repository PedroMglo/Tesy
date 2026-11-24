"""Run a tiny pinned stock ClassLRU fixture and bound the chosen GGUF/CUDA buffers."""

import argparse
import json
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"
HERE = Path(__file__).resolve().parent
SOURCES = [
    "src/llama-moe-cache.cpp",
    "src/llama-model-loader.cpp",
    "src/llama-model.cpp",
    "src/llama-mmap.cpp",
    "src/llama-graph.cpp",
    "src/models/openai-moe.cpp",
    "src/llama-kv-cache.cpp",
    "src/llama-kv-cache-iswa.cpp",
    "ggml/src/ggml-cuda/ggml-cuda.cu",
    "ggml/src/ggml-cuda/common.cuh",
    "ggml/src/ggml-backend.cpp",
    "common/arg.cpp",
    "common/common.h",
    "docs/moe-cache.md",
]
PREAMBLE = """
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <vector>
#define GGML_ASSERT(x) assert(x)
#define GGML_ABORT(...) std::abort()
"""
MAIN = """
int main(int argc, char **argv) {
    if (argc != 2) return 1;
    const int n_slots = std::stoi(argv[1]);
    moe_cache_lru lru;
    lru.init(36, 128, n_slots);
    std::vector<std::vector<int32_t>> maps(36, std::vector<int32_t>(128, n_slots));
    for (int i = 0; i < 36; ++i) lru.slot_map[i] = maps[i].data();
    std::vector<moe_cache_lru::fill> fills, cpu;
    size_t hits = 0;
    auto run = [&](int layer, int count, int expected_hits, int expected_fills) {
        std::vector<int32_t> ids(count);
        for (int i = 0; i < count; ++i) ids[i] = i;
        bool ok = lru.plan(layer, ids.data(), ids.size(), count/4, 4, 0,
                           [](size_t) { return size_t{0}; }, fills, cpu, hits);
        return ok && cpu.empty() && hits == size_t(expected_hits) &&
               fills.size() == size_t(expected_fills);
    };
    if (!run(0, 4, 0, 4)) return 2;
    if (!run(0, 4, 4, 0)) return 3;
    if (!run(1, 128, 0, 128)) return 4;
    if (!run(1, 128, 128, 0)) return 5;
    std::puts("PASS_PINNED_CLASSLRU_DECODER_AND_UB32");
}
"""


def require(value, reason):
    if not value:
        raise ValueError(reason)


def probe(upstream):
    def blob(name):
        return subprocess.check_output(
            ["git", "-C", upstream, "show", PIN + ":" + name], timeout=15
        )

    pins = {name: sha256(blob(name)).hexdigest() for name in SOURCES}
    protocol_digest = sha256((HERE / "stock_cache.md").read_bytes()).hexdigest()
    require(
        protocol_digest == "1184a7283d24ccdea827535c9a4adf4ba17654f45a32f04800d7d629c39bfa1a",
        "stock protocol changed",
    )
    header_blob = (HERE / "moestream-receipt.json").read_bytes()
    require(
        sha256(header_blob).hexdigest()
        == "e83ab2ab55961429a8374f21f10b7a2141f1dd48801f9a101abbe98cb7c0bd70",
        "header receipt",
    )
    header = json.loads(header_blob)
    layers, experts, hidden, vocab = 36, 128, 2880, 201088
    cache_budget = 2048 * 2**20
    role = header["expert_role_bytes"]
    require(role == hidden * hidden // 32 * 17, "MXFP4 geometry")
    gpu_alignment = 128

    def pad(n):
        return (n + gpu_alignment - 1) // gpu_alignment * gpu_alignment

    def bank_charge(usable):
        return 3 * pad((usable + 1) * role)

    slots = cache_budget // (3 * role) - 1
    require(bank_charge(slots) <= cache_budget < bank_charge(slots + 1), "slot budget")
    # For quantized weights CUDA can read past the final row and pads to 512 elements.
    guard_bytes = (512 - hidden % 512) // 32 * 17
    bank_alloc = 3 * pad((slots + 1) * role + guard_bytes)
    kv = 18 * (8192 + 256) * 8 * 64 * 2 * 2
    expert_weight = 3 * role * experts * layers
    expert_bias = 3 * layers * hidden * experts * 4
    token_embedding = hidden * vocab // 32 * 34
    fixed_gpu = header["other_encoded_bytes"] - expert_bias - token_embedding
    cache_source = blob("src/llama-moe-cache.cpp").decode()
    cls = cache_source[
        cache_source.index("struct moe_cache_lru {") : cache_source.index(
            "static std::vector<ggml_tensor *> llama_moe_cache_layer_experts"
        )
    ]
    code = PREAMBLE + cls + MAIN
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp) / "stock.cpp"
        binary = Path(tmp) / "stock-lru"
        cpp.write_text(code)
        subprocess.run(
            ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", cpp, "-o", binary],
            check=True,
            timeout=40,
        )
        result = subprocess.check_output([binary, str(slots)], text=True, timeout=5).strip()
    require(result == "PASS_PINNED_CLASSLRU_DECODER_AND_UB32", "planner fixture")
    return {
        "scope": "FORMAL_SOURCE_PLUS_MODEL_FREE_PLANNER",
        "pin": PIN,
        "source_sha256": pins,
        "protocol_sha256": protocol_digest,
        "header_sha256": header["verified"]["header_sha256"],
        "fixture_sha256": sha256(code.encode()).hexdigest(),
        "fixture": result,
        "budget_bytes": cache_budget,
        "usable_shared_slots": slots,
        "cache_encoded_bytes_with_guard_slot": bank_charge(slots),
        "cache_cuda_128_aligned_bank_bytes_with_row_guards": bank_alloc,
        "all_expert_encoded_bytes_host_mapped": expert_weight,
        "all_expert_bias_encoded_bytes_host_mapped": expert_bias,
        "token_embedding_encoded_bytes_host_mapped": token_embedding,
        "nonexpert_gpu_encoded_bytes_if_all_supported": fixed_gpu,
        "visible_cpu_slot_map_bytes": 36 * 128 * 4,
        "kv_f16_bytes": kv,
        "packed_gpu_budget_left_before_graph_and_runtime": 8053063680 - fixed_gpu - bank_alloc - kv,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--llama-git", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(exist_ok=False)
    try:
        result = probe(a.llama_git)
    except Exception as err:
        (a.new_output_dir / "FAIL.txt").write_text(type(err).__name__ + "\n")
        raise
    tmp = a.new_output_dir / ".receipt.pending"
    tmp.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
