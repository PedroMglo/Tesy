#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from tesy.inventory import TensorRecord, build_expert_inventory, write_json_no_replace
from tesy.models import get_model, load_lock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--llama-dir",
        type=Path,
        default=Path(os.environ.get("TESY_LLAMA_DIR", ".deps/llama.cpp")),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to replace existing output: {args.output}")

    lock = load_lock()
    model = get_model(lock, args.model_id)
    expected_layers = model["upstream"]["layers"]
    expected_experts = model["upstream"]["experts"]

    gguf_py = args.llama_dir.resolve() / "gguf-py"
    if not gguf_py.is_dir():
        raise SystemExit(
            f"missing pinned gguf-py at {gguf_py}; run scripts/bootstrap_llama_cpp.sh"
        )
    sys.path.insert(0, str(gguf_py))
    try:
        from gguf import GGUFReader
    except ImportError as exc:
        raise SystemExit(
            "cannot import pinned gguf-py. Install its local dependencies in the "
            "Tesy virtualenv, e.g. python -m pip install -e .deps/llama.cpp/gguf-py"
        ) from exc

    reader = GGUFReader(args.model_path, "r")
    records = [
        TensorRecord(
            name=tensor.name,
            shape=tuple(int(value) for value in tensor.shape),
            n_bytes=int(tensor.n_bytes),
        )
        for tensor in reader.tensors
    ]
    payload = build_expert_inventory(
        records,
        model_id=args.model_id,
        expected_layers=int(expected_layers),
        expected_experts=int(expected_experts),
    )
    payload["model_file"] = {
        "path": str(args.model_path.resolve()),
        "bytes": args.model_path.stat().st_size,
    }
    payload["gguf_reader_source"] = str(gguf_py)
    write_json_no_replace(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
