"""Bound original C281 process counters under one unknown monotonic monitor epoch."""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import pairwise
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
NS = 10**9
KEYS = ("read_bytes", "rchar", "syscr")
SOURCE = {
    "tools/run_bounded.py": "e6f404e06036ce9df9fcca048d193710e75b37729fc2df411bf417034a7d347b",
    "tools/optin_integration_client.py": (
        "2cca03a7262a0715338ffd73e7ec3ca4d129dfa5f03760fe36971b51d46d31b9"
    ),
}
NATIVE = {
    "tools/server/server-context.cpp": (
        "657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55"
    ),
    "ggml/src/ggml.c": "ef2a64f06c900993396612ab2bfb98238d5ea931abbc938ddb0c72d31a0bd043",
}
RECEIPT = "cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a"
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
MARGIN = 2_000  # ns, exterior tolerance on microsecond native clock and floats


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes(), parse_float=Decimal)


def lines(path):
    return [json.loads(line, parse_float=Decimal) for line in path.read_bytes().splitlines()]


def ns(seconds, rounding=ROUND_FLOOR):
    return int((Decimal(seconds) * NS).to_integral_value(rounding=rounding))


@dataclass(frozen=True)
class Sample:
    lo: int
    hi: int
    counters: tuple


@dataclass(frozen=True)
class Phase:
    first_min: int
    first_max: int
    end_min: int
    end_max: int


def extrema(samples, phase, max_shift):
    """Scan all piecewise-constant observation sets on the integer ns clock."""
    require(
        max_shift >= 0 and phase.first_min <= phase.first_max <= phase.end_min <= phase.end_max,
        "clock bounds",
    )
    changes = {0, max_shift}
    for s in samples:
        for cut in (
            phase.first_min - s.hi,
            phase.first_max - s.lo,
            phase.end_min - s.hi,
            phase.end_max - s.lo,
        ):
            if 0 <= cut <= max_shift:
                changes.add(cut)
    offsets = sorted(changes)
    points = changes | {(a + b) // 2 for a, b in pairwise(offsets) if b - a > 1}
    lowers, uppers, counts = [], [], []
    for off in points:
        inside = [
            s for s in samples if phase.first_max <= s.lo + off and s.hi + off <= phase.end_min
        ]
        before = [s for s in samples if s.hi + off <= phase.first_min]
        after = [s for s in samples if phase.end_max <= s.lo + off]
        counts.append(len(inside))
        lowers.append(
            tuple(b - a for a, b in zip(inside[0].counters, inside[-1].counters, strict=True))
            if len(inside) >= 2
            else (0,) * len(KEYS)
        )
        uppers.append(
            tuple(b - a for a, b in zip(before[-1].counters, after[0].counters, strict=True))
            if before and after
            else None
        )
    result = {
        k: {
            "min": min(x[i] for x in lowers),
            "max": max(x[i] for x in uppers) if all(v is not None for v in uppers) else None,
        }
        for i, k in enumerate(KEYS)
    }
    require(
        all(v["min"] >= 0 and (v["max"] is None or v["min"] <= v["max"]) for v in result.values()),
        "nonconserving counter",
    )
    return dict(
        counters=result,
        definitely_inside_samples=[min(counts), max(counts)],
        tested_offsets=len(points),
        change_points=len(changes),
    )


def between(start, end):
    return Phase(start - MARGIN, start + MARGIN, end - MARGIN, end + MARGIN)


def auth(root, backend):
    for folder, manifest in ((REPO, SOURCE), (backend, NATIVE)):
        for name, digest in manifest.items():
            require(sha(folder / name) == digest, "source identity: " + name)
    compact = HERE.parent / "postupdate" / "compact.py"
    spec = importlib.util.spec_from_file_location("phase_reads_c281", compact)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed = module.summarize(REPO, root, RECEIPT)
    reference = HERE.parent / "postupdate/physical-r01/evidence.json"
    require(
        observed == json.loads(reference.read_bytes()),
        "mismatch with authenticated full file manifest",
    )
    return observed


def phase_observations(root, *, verified_cleanup_ns=None):
    raw = root / "raw"
    preset = read(root / "preset.json")
    require(preset["model_sha256"] == MODEL, "model identity")
    stem = preset["run_id"]
    launch = read(raw / (stem + ".launch.json"))
    client = read(root / "client-receipt.json")
    monitor = read(raw / (stem + ".json"))
    pid = client["process_identity"]
    require(pid == launch["process_identity"] == monitor["process_identity"], "monitor/client PID")
    require(sha(raw / (stem + ".launch.json")) == client["launch_sha256"], "launch identity")
    start = launch["start_inventory"]["popen_invoked_monotonic_ns"]
    max_shift = ns(client["ready_monotonic"], ROUND_CEILING) + MARGIN - start
    if verified_cleanup_ns is not None:
        # The controller reads the finished manifest before taking this timestamp.
        elapsed_lower_ns = ns(monitor["elapsed_s"]) - 500_001
        max_shift = min(max_shift, verified_cleanup_ns - elapsed_lower_ns - start)
        require(max_shift >= 0, "empty monitor epoch intersection")
    samples = []
    fds = Counter()
    for row in lines(raw / (stem + ".samples.jsonl")):
        require(row["pid"] == pid["pid"] and row["process_identity"] == pid, "sample identity")
        fd = row["model_fds"]
        require(fd["open"] == fd["direct"] and fd["buffered"] == 0, "model FD accounting")
        fds[fd["direct"]] += 1
        t = start + ns(row["elapsed_s"])
        c = tuple(row["proc"][k] for k in KEYS)
        require(all(type(x) is int and x >= 0 for x in c), "missing/invalid counter")
        s = Sample(t - 500_001 - ns(row["collection_s"], ROUND_CEILING), t + 500_001, c)
        if samples:
            prev = samples[-1]
            require(
                prev.hi < s.lo and all(a <= b for a, b in zip(prev.counters, c, strict=True)),
                "sample order or reset",
            )
        samples.append(s)
    turns = []
    for i in (1, 2):
        full = read(raw / f"T{i}-result.json")
        journal = lines(raw / f"T{i}-request.jsonl")
        require(full["accepted"] and journal[-1]["accepted"], "accepted terminal")
        s, e = (ns(full[k]) for k in ("request_started_monotonic", "request_ended_monotonic"))
        validated = ns(journal[-1]["monotonic_s"])
        t = full["timings"]
        p, d = (ns(t[k] / 1000) for k in ("prompt_ms", "predicted_ms"))
        first_final = ns(full["stream_metrics"]["first_final_content_chunk_s"])
        require(s + p + d <= e <= validated and t["predicted_n"] > 0, "native/client chronology")
        phases = {
            "native_prompt": Phase(s - MARGIN, e - p - d + MARGIN, s + p - MARGIN, e - d + MARGIN),
            "native_decode": Phase(s + p - MARGIN, e - d + MARGIN, s + p + d - MARGIN, e + MARGIN),
            "client_first_final": between(s, s + first_final),
            "client_transport": between(s, e),
            "client_validated": between(s, validated),
        }
        bounded = {name: extrema(samples, v, max_shift) for name, v in phases.items()}
        turns.append(
            dict(
                turn=i,
                cache_n=t["cache_n"],
                prompt_n=t["prompt_n"],
                predicted_n=t["predicted_n"],
                prompt_ns=p,
                decode_ns=d,
                transport_minus_native_ns=e - s - p - d,
                first_final_ns=first_final,
                transport_ns=e - s,
                validated_ns=validated - s,
                phases=bounded,
            )
        )
    return dict(
        backend_commit=monitor["backend_sha"],
        samples=len(samples),
        sample_fd_counts=dict(fds),
        common_epoch_width_ns=max_shift,
        sample_support_extra_ns=500_001,
        boundary_margin_ns=MARGIN,
        turns=turns,
    )


def analyze(root, backend):
    reference = auth(root, backend)
    observed = phase_observations(root)
    n = observed["turns"][1]
    # Ceiling is optimistic by <1 ns, including the exact rational predicted_n / 6.
    budget_ns = (
        n["prompt_ns"]
        + 10 * NS
        - n["first_final_ns"]
        + n["decode_ns"]
        - (n["predicted_n"] * NS // 6)
    )
    require(budget_ns > 0, "no positive conditional prompt budget")
    threshold = (4_500_000_000 * budget_ns + NS - 1) // NS
    bounds = n["phases"]["native_prompt"]["counters"]["read_bytes"]
    status = (
        "NO_GO_SERVICE_FIXED"
        if bounds["min"] > threshold
        else "HEADROOM"
        if bounds["max"] is not None and bounds["max"] <= threshold
        else "INCONCLUSIVE"
    )
    return dict(
        status=status,
        receipt_sha256=RECEIPT,
        raw_manifest_sha256=reference["files_sha256"],
        source_sha256={**SOURCE, **NATIVE},
        measurement_commit=reference["measurement_commit"],
        **observed,
        conditional=dict(
            prompt_budget_ns_rounded_up=budget_ns,
            assumed_Bps=4_500_000_000,
            available_bytes_rounded_up=threshold,
            required_saving_min_bytes=max(0, bounds["min"] - threshold),
            minimum_required_Bps_floor=bounds["min"] * NS // budget_ns,
        ),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-root", "backend", "new-output-dir"):
        ap.add_argument("--" + name, type=Path, required=True)
    args = ap.parse_args()
    output = analyze(args.raw_root.resolve(strict=True), args.backend.resolve(strict=True))
    args.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    with (args.new_output_dir / "evidence.json").open("x") as stream:
        json.dump(output, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
