#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from tesy.expert_inventory import (
    TensorRecord,
    build_expert_inventory,
    write_json_no_replace,
)
from tesy.models import get_model, load_lock


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--llama-dir",
        type=Path,
        default=Path(
            os.environ.get("TESY_LLAMA_CPP_DIR", ".deps/llama.cpp")
        ),
    )
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace existing output: {args.output}")

    model = get_model(load_lock(), args.model_id)
    gguf_py = args.llama_dir.resolve() / "gguf-py"
    if not gguf_py.is_dir():
        raise SystemExit(
            f"missing pinned gguf-py at {gguf_py}; "
            "run scripts/bootstrap_llama_cpp.sh"
        )
    sys.path.insert(0, str(gguf_py))
    try:
        from gguf import GGUFReader
    except ImportError as exc:
        raise SystemExit(
            "cannot import pinned gguf-py; install it into the Tesy virtualenv: "
            "python -m pip install -e .deps/llama.cpp/gguf-py"
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
        expected_layers=int(model["upstream"]["layers"]),
        expected_experts=int(model["upstream"]["experts"]),
    )
    payload["model_file"] = {
        "path": str(args.model_path.resolve()),
        "bytes": args.model_path.stat().st_size,
    }
    payload["gguf_reader"] = {
        "source": "pinned llama.cpp/gguf-py",
        "path": str(gguf_py),
    }
    write_json_no_replace(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
