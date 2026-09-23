from __future__ import annotations

import importlib
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tesy.backend import BackendError, verify_source_state
from tesy.models import ModelLockError, inspect_model_file


class ExpertInventoryError(ValueError):
    pass


_EXPERT_TENSOR = re.compile(
    r"^blk\.(?P<layer>\d+)\.(?P<body>[^.]*_exps)(?:\.(?P<suffix>.+))?$"
)


@dataclass(frozen=True)
class TensorRecord:
    name: str
    shape: tuple[int, ...]
    n_bytes: int
    tensor_type: str
    data_offset: int


def _validate_record(record: TensorRecord) -> None:
    if not record.name:
        raise ExpertInventoryError("tensor name must be non-empty")
    if not record.shape or any(
        isinstance(dim, bool) or not isinstance(dim, int) or dim <= 0
        for dim in record.shape
    ):
        raise ExpertInventoryError(f"invalid shape for {record.name}: {record.shape}")
    if (
        isinstance(record.n_bytes, bool)
        or not isinstance(record.n_bytes, int)
        or record.n_bytes <= 0
    ):
        raise ExpertInventoryError(f"invalid byte size for {record.name}")
    if (
        isinstance(record.data_offset, bool)
        or not isinstance(record.data_offset, int)
        or record.data_offset < 0
    ):
        raise ExpertInventoryError(f"invalid data offset for {record.name}")


def derive_expert_payload_inventory(
    tensors: Iterable[TensorRecord],
) -> dict[str, Any]:
    """Derive equal-slice encoded payload bytes from merged expert tensors.

    For llama.cpp GGUF MoE tensors such as blk.N.ffn_gate_exps.weight, the
    expert dimension is the final logical GGUF dimension. Division of the
    encoded tensor payload by that dimension is admitted only when exact.
    """
    grouped: dict[int, list[TensorRecord]] = {}
    rejected: list[dict[str, Any]] = []

    for record in tensors:
        _validate_record(record)
        match = _EXPERT_TENSOR.match(record.name)
        if not match:
            continue
        layer = int(match.group("layer"))
        grouped.setdefault(layer, []).append(record)

    if not grouped:
        return {
            "schema": "tesy.gguf_expert_inventory.v1",
            "classification": "GGUF_ENCODED_PAYLOAD_DERIVED",
            "status": "INCONCLUSIVE",
            "layers": [],
            "rejected": [],
            "reason": "no merged *_exps tensors were found",
            "claim_boundary": _claim_boundary(),
        }

    layers: list[dict[str, Any]] = []
    for layer, records in sorted(grouped.items()):
        expert_counts = {record.shape[-1] for record in records}
        if len(expert_counts) != 1:
            rejected.append(
                {
                    "layer": layer,
                    "reason": "expert dimension mismatch across merged tensors",
                    "tensors": [record.name for record in records],
                }
            )
            continue

        expert_count = next(iter(expert_counts))
        tensor_rows: list[dict[str, Any]] = []
        per_expert_total = 0
        layer_total = 0
        layer_valid = True

        for record in sorted(records, key=lambda item: item.name):
            if record.n_bytes % expert_count != 0:
                rejected.append(
                    {
                        "layer": layer,
                        "tensor": record.name,
                        "reason": (
                            f"encoded payload {record.n_bytes} is not divisible "
                            f"by expert_count {expert_count}"
                        ),
                    }
                )
                layer_valid = False
                continue

            bytes_per_expert = record.n_bytes // expert_count
            per_expert_total += bytes_per_expert
            layer_total += record.n_bytes
            tensor_rows.append(
                {
                    "name": record.name,
                    "shape": list(record.shape),
                    "tensor_type": record.tensor_type,
                    "data_offset": record.data_offset,
                    "encoded_tensor_bytes": record.n_bytes,
                    "encoded_payload_bytes_per_expert": bytes_per_expert,
                }
            )

        if not layer_valid:
            continue

        layers.append(
            {
                "layer": layer,
                "expert_count": expert_count,
                "merged_tensor_count": len(tensor_rows),
                "encoded_expert_tensor_bytes_total": layer_total,
                "encoded_payload_bytes_per_expert": per_expert_total,
                "tensors": tensor_rows,
            }
        )

    status = "PASS_DERIVATION" if layers and not rejected else "INCONCLUSIVE"
    return {
        "schema": "tesy.gguf_expert_inventory.v1",
        "classification": "GGUF_ENCODED_PAYLOAD_DERIVED",
        "status": status,
        "layers": layers,
        "rejected": rejected,
        "total_merged_expert_tensor_bytes": sum(
            row["encoded_expert_tensor_bytes_total"] for row in layers
        ),
        "claim_boundary": _claim_boundary(),
    }


def _claim_boundary() -> str:
    return (
        "Encoded GGUF tensor payload accounting only. Per-expert values are exact "
        "integer slices of merged expert tensor payloads when the final expert "
        "dimension divides n_bytes. They are not physical NVMe reads, page-cache "
        "traffic, DRAM traffic, PCIe traffic, allocation size, or proof that an "
        "individual expert is physically fetched as one contiguous range."
    )


def _load_pinned_gguf_reader(llama_source: Path):
    source_state = verify_source_state(llama_source)
    if source_state["probe_status"] != "PASS":
        raise ExpertInventoryError(
            "llama.cpp source must match the pinned clean backend commit"
        )

    gguf_root = Path(source_state["path"]) / "gguf-py"
    if not (gguf_root / "gguf" / "gguf_reader.py").is_file():
        raise ExpertInventoryError(f"pinned gguf-py not found at {gguf_root}")

    root_text = str(gguf_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    try:
        module = importlib.import_module("gguf.gguf_reader")
    except ImportError as exc:
        raise ExpertInventoryError(
            "cannot import pinned gguf-py; install its declared Python "
            "dependencies in the Tesy virtualenv"
        ) from exc

    module_file = Path(module.__file__).resolve()
    try:
        module_file.relative_to(gguf_root.resolve())
    except ValueError as exc:
        raise ExpertInventoryError(
            f"gguf module was loaded from an unpinned location: {module_file}"
        ) from exc
    return module.GGUFReader, source_state


def inspect_gguf_experts(
    model_path: Path,
    llama_source: Path,
) -> dict[str, Any]:
    try:
        model = inspect_model_file(model_path, with_sha256=False)
    except ModelLockError as exc:
        raise ExpertInventoryError(str(exc)) from exc

    try:
        GGUFReader, source_state = _load_pinned_gguf_reader(llama_source)
    except BackendError as exc:
        raise ExpertInventoryError(str(exc)) from exc

    reader = GGUFReader(model["path"])
    records = [
        TensorRecord(
            name=tensor.name,
            shape=tuple(int(value) for value in tensor.shape.tolist()),
            n_bytes=int(tensor.n_bytes),
            tensor_type=tensor.tensor_type.name,
            data_offset=int(tensor.data_offset),
        )
        for tensor in reader.tensors
    ]
    result = derive_expert_payload_inventory(records)
    result["model"] = {
        "path": model["path"],
        "size_bytes": model["size_bytes"],
    }
    result["backend_source"] = source_state
    result["tensor_count_total"] = len(records)
    return result
