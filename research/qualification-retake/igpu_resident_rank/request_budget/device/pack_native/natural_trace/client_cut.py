"""Locate the first final sample and bound its local delivery delay on CLOCK_MONOTONIC."""

import hashlib
import json
import math
from pathlib import Path
from runpy import run_path

QUAL = Path(__file__).resolve().parents[5]
VERIFY = run_path(str(QUAL / "history_lookup/native_ids/verify.py"))
TEXT_CUT = run_path(str(QUAL / "history_lookup/packed_step_budget/screen.py"))["text_cut"]


def upper_bounds(start_s, first_final_s, calls, sample):
    if not (1 <= sample < len(calls) and calls[sample]["number"] == sample + 1):
        raise ValueError("sample/call mapping")
    admission = calls[0]["enter_begin_ns"] - math.floor(start_s * 1e9)
    after_return = math.ceil(first_final_s * 1e9) - calls[sample]["return_ns"]
    if min(admission, after_return) < 0:
        raise ValueError("client/native causal order")
    return {
        "sample_number": sample,
        "sample_call": sample + 1,
        "start_to_first_native_enter_ns": admission,
        "last_relevant_return_to_first_final_ns": after_return,
    }


def inspect(arm, receipt, calls):
    raw = arm / "raw"
    identity = receipt["native_ids"]
    name = identity["raw_stderr_file"]
    if Path(name).name != name or identity["verbosity"] != 5:
        raise ValueError("log identity")
    log = (raw / name).read_bytes()
    if hashlib.sha256(log).hexdigest() != identity["stderr_sha256"]:
        raise ValueError("unsealed producer")
    turns = VERIFY["trajectories"](log)
    projections = []
    for i, (samples, expected, geometry) in enumerate(
        zip(turns, receipt["trajectories"], VERIFY["GEOMETRY"], strict=True), 1
    ):
        proj = VERIFY["projection"](raw, i, geometry)
        payload = json.dumps(proj, sort_keys=True, separators=(",", ":")).encode()
        ids = VERIFY["ids_bytes"]([token for token, _ in samples])
        if (hashlib.sha256(payload).hexdigest(), hashlib.sha256(ids).hexdigest()) != (
            expected["projected_sha256"],
            expected["sampled_ids_sha256"],
        ):
            raise ValueError("official request, IDs or frames changed")
        projections.append(proj)
    fragments = []
    for line in (raw / "T2-request.jsonl").read_bytes().splitlines():
        o = json.loads(line)
        if o["kind"] != "SSE_FRAGMENT":
            continue
        s = o["fragment"].strip()
        if s.startswith("data: {"):
            fragments.append((json.loads(s[6:]), o["monotonic_s"]))
    projected = projections[1][2]
    # Projection omits the server's varying request identifiers and wall timestamps.
    deltas = [
        (text.encode(), t)
        for frame, t in fragments
        for choice in frame.get("choices", [])
        if (text := choice["delta"].get("content"))
    ]
    baseline = [
        text.encode()
        for f in projected
        for c in f.get("choices", [])
        if (text := c["delta"].get("content"))
    ]
    if not deltas or [s for s, _ in deltas] != baseline:
        raise ValueError("actual content frames")
    pieces = [log[pos : log.index(b"'\n", pos)] for _, pos in turns[1]]
    idx = TEXT_CUT(pieces, baseline)
    if idx != 44:
        raise ValueError("unidentified first final sample")
    result = json.loads((raw / "T2-result.json").read_bytes())
    start = result["request_started_monotonic"]
    measured = result["stream_metrics"]["first_final_content_chunk_s"]
    observed = deltas[0][1]
    if abs(observed - start - measured) > 0.001:
        raise ValueError("client clock disagreement")
    # Allow both the timestamp taken for the SSE row and the separately recorded metric.
    evidence = upper_bounds(start, max(observed, start + measured), calls, idx + 1)
    return evidence | {
        "first_frame_minus_metric_ns": round((observed - start - measured) * 1e9),
        "native_log_time_used": False,
    }
