"""Read the C281 client clocks from its accepted terminal and the frozen ID representation."""

import json


def summarize(row, raw, i, *, ids_hash):
    events = [json.loads(line) for line in (raw / f"T{i}-request.jsonl").read_text().splitlines()]
    terminal = events[-1]
    if not (terminal["kind"] == "REQUEST_TERMINAL" and terminal["accepted"] and row["accepted"]):
        raise ValueError("terminal")
    t = row["timings"]
    return dict(
        official_ids_sha256=ids_hash(row["official_ids"]),
        prompt=len(row["official_ids"]),
        cached=t["cache_n"],
        evaluated=t["prompt_n"],
        output=row["usage"]["completion_tokens"],
        predicted=t["predicted_n"],
        prefill_s=t["prompt_ms"] / 1000,
        decode_s=t["predicted_ms"] / 1000,
        decode_tok_s=t["predicted_per_second"],
        first_reasoning_s=row["stream_metrics"]["first_reasoning_chunk_s"],
        first_final_s=row["stream_metrics"]["first_final_content_chunk_s"],
        transport_s=row["request_wall_s"],
        valid_s=terminal["monotonic_s"] - row["request_started_monotonic"],
        validator=row["content_gate"],
        stop=row["finish_reason"],
        output_ids_authority=row["output_ids_authority"],
    )
