from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tesy.gguf_inventory import TensorRecord, derive_expert_payload_inventory


class NativeGGUFInventoryError(ValueError):
    pass


def _load_line(raw: str, *, line_number: int) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NativeGGUFInventoryError(
            f"invalid JSON at line {line_number}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise NativeGGUFInventoryError(
            f"line {line_number} must be a JSON object"
        )
    return payload


def parse_native_inventory_jsonl(text: str) -> tuple[dict[str, Any], list[TensorRecord]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise NativeGGUFInventoryError("native inventory is empty")

    header = _load_line(lines[0], line_number=1)
    if header.get("schema") != "tesy.gguf_native_inventory_header.v1":
        raise NativeGGUFInventoryError("unsupported native inventory header schema")

    tensor_count = header.get("tensor_count")
    data_offset = header.get("data_offset")
    alignment = header.get("alignment")
    gguf_version = header.get("gguf_version")
    for name, value in {
        "tensor_count": tensor_count,
        "data_offset": data_offset,
        "alignment": alignment,
        "gguf_version": gguf_version,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise NativeGGUFInventoryError(f"invalid header field: {name}")

    if len(lines) - 1 != tensor_count:
        raise NativeGGUFInventoryError(
            f"tensor count mismatch: {len(lines) - 1} != {tensor_count}"
        )

    records: list[TensorRecord] = []
    names: set[str] = set()
    for expected_id, raw in enumerate(lines[1:]):
        payload = _load_line(raw, line_number=expected_id + 2)
        if payload.get("schema") != "tesy.gguf_native_tensor.v1":
            raise NativeGGUFInventoryError(
                f"unsupported tensor schema at id {expected_id}"
            )
        if payload.get("id") != expected_id:
            raise NativeGGUFInventoryError(
                f"tensor id mismatch: {payload.get('id')!r} != {expected_id}"
            )

        name = payload.get("name")
        tensor_type = payload.get("tensor_type")
        shape = payload.get("shape")
        n_bytes = payload.get("n_bytes")
        relative = payload.get("relative_data_offset")
        absolute = payload.get("data_offset")

        if not isinstance(name, str) or not name:
            raise NativeGGUFInventoryError(f"invalid tensor name at id {expected_id}")
        if name in names:
            raise NativeGGUFInventoryError(f"duplicate tensor name: {name}")
        names.add(name)

        if not isinstance(tensor_type, str) or not tensor_type:
            raise NativeGGUFInventoryError(f"invalid tensor type for {name}")
        if (
            not isinstance(shape, list)
            or not shape
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                for value in shape
            )
        ):
            raise NativeGGUFInventoryError(f"invalid tensor shape for {name}")
        for field_name, value in {
            "n_bytes": n_bytes,
            "relative_data_offset": relative,
            "data_offset": absolute,
        }.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise NativeGGUFInventoryError(
                    f"invalid {field_name} for {name}"
                )
        if n_bytes <= 0:
            raise NativeGGUFInventoryError(f"invalid n_bytes for {name}")
        if absolute != data_offset + relative:
            raise NativeGGUFInventoryError(
                f"absolute data offset mismatch for {name}"
            )

        records.append(
            TensorRecord(
                name=name,
                shape=tuple(shape),
                n_bytes=n_bytes,
                tensor_type=tensor_type,
                data_offset=absolute,
            )
        )

    return header, records


def derive_native_expert_inventory(text: str) -> dict[str, Any]:
    header, records = parse_native_inventory_jsonl(text)
    payload = derive_expert_payload_inventory(records)
    payload["native_metadata_source"] = {
        "schema": header["schema"],
        "gguf_version": header["gguf_version"],
        "alignment": header["alignment"],
        "data_offset": header["data_offset"],
        "tensor_count": header["tensor_count"],
    }
    payload["tensor_count_total"] = len(records)
    payload["claim_boundary"] = (
        payload["claim_boundary"]
        + " Tensor metadata was read by a native helper linked to the pinned "
        "llama.cpp gguf/ggml implementation; no gguf-py or third-party Python "
        "dependency is used for this derivation."
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    raw = args.input.read_text(encoding="utf-8")
    payload = derive_native_expert_inventory(raw)
    payload["raw_inventory_sha256"] = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")

    return 0 if payload.get("status") == "PASS_DERIVATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
