"""Static, pinned-source screen of upstream llama.cpp GPT-OSS expert loading.

This checks source structure only. It does not establish model fit, fidelity, or speed.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


FILES = (
    "src/models/openai-moe.cpp",
    "src/llama-model-loader.cpp",
    "src/llama-model-loader.h",
    "src/llama-model.cpp",
    "common/arg.cpp",
    "src/llama-arch.cpp",
    "ggml/src/ggml-cuda/mmq-config-ampere.cuh",
)


def screen(source: Path) -> dict:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip()
    if dirty:
        raise ValueError("source checkout is dirty")
    data = {name: (source / name).read_bytes() for name in FILES}
    model = data["src/models/openai-moe.cpp"].decode()
    loader = data["src/llama-model-loader.cpp"].decode()
    header = data["src/llama-model-loader.h"].decode()
    args = data["common/arg.cpp"].decode()
    arch = data["src/llama-arch.cpp"].decode()
    cuda = data["ggml/src/ggml-cuda/mmq-config-ampere.cuh"].decode()
    expert_lines = [line.strip() for line in model.splitlines()
                    if "create_tensor(" in line and "LLM_TENSOR_FFN_" in line
                    and "EXPS" in line and '"weight"' in line]
    checks = {
        "architecture_registered": 'LLM_ARCH_OPENAI_MOE,       "gpt-oss"' in arch,
        "model_recognizes_36_layers_as_120b": "case 36: type = LLM_TYPE_120B" in model,
        "mxfp4_ampere_kernel_config_present": "CASE(GGML_TYPE_MXFP4" in cuda,
        "expert_weights_not_marked_lazy": len(expert_lines) == 3 and all(line.endswith(", 0);") for line in expert_lines),
        "lazy_requires_explicit_tensor_flag": "if (flags & TENSOR_READ_LAZY)" in loader,
        "lazy_mode_is_mmap_based": "read rows on demand instead of loading whole tensor; requires mmap" in header,
        "lazy_cli_targets_certain_tensors": "on-demand reading of certain tensors" in args,
        "mmap_and_direct_io_are_separate_load_modes": "LLAMA_LOAD_MODE_MMAP" in loader and "LLAMA_LOAD_MODE_DIRECT_IO" in loader,
    }
    if not all(checks.values()):
        raise ValueError(f"source structure changed: {checks}")
    return {
        "schema": "c116-upstream-source-screen-v1",
        "evidence_class": "SOURCE_AUDITED",
        "source_repo": "https://github.com/ggml-org/llama.cpp",
        "source_commit": head,
        "source_dirty": False,
        "source_file_sha256": {name: hashlib.sha256(body).hexdigest() for name, body in data.items()},
        "checks": checks,
        "expert_weight_source_lines": expert_lines,
        "interpretation": "GPT-OSS/MXFP4 implementation exists, but this source pin does not mark GPT-OSS expert weights for its explicit lazy row-loading path. Ordinary mmap/page cache may still permit bounded operation; fit, numerical coverage, and speed on the target are NOT_RUN.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = screen(args.source)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")


if __name__ == "__main__":
    main()
