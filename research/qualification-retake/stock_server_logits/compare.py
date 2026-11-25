"""Reconcile sealed client/capture/server evidence after exit and compare complete F32 rows."""

import argparse
import json
import math
import re
import struct
from pathlib import Path

from inputs import VOCAB, digest, load_prompt, require

ARMS = ("S", "A", "B", "B20")
SERVER = "2396cc20738e1c2b7d8bfbe209b89098874683c424518d4bf139f7f51e9cfe00"
STOCK = "717a7e3dc18ae58585c6df1af2454c5b441c171258b7100ae7e11530e02265b8"
CAND = "34ce470fac8b70d58602ba979f014616b9a8b7a9593b55a5e8436116f6ceb767"
CALLER = "7cf9543328e80642d8c5d2212b1926fa5dc66f551d3d1e4cf04ab7900622c5e3"


def summarize(reference, candidate, *, vocab=VOCAB):
    require(
        vocab > 0 and len(reference) == len(candidate) == 4 * vocab,
        "full little-endian F32 row size",
    )
    x = struct.unpack(f"<{vocab}f", reference)
    y = struct.unpack(f"<{vocab}f", candidate)
    finite_x = all(map(math.isfinite, x))
    finite_y = all(map(math.isfinite, y))
    both = finite_x and finite_y
    distances = [abs(a - b) for a, b in zip(x, y, strict=True)] if both else []
    return dict(
        bitwise_equal=reference == candidate,
        different_f32_bits=sum(
            a != b
            for a, b in zip(
                struct.iter_unpack("<I", reference),
                struct.iter_unpack("<I", candidate),
                strict=True,
            )
        ),
        finite_gold=finite_x,
        finite_candidate=finite_y,
        gold_argmax=max(range(vocab), key=x.__getitem__) if finite_x else None,
        candidate_argmax=max(range(vocab), key=y.__getitem__) if finite_y else None,
        gold_sha256=digest(reference),
        candidate_sha256=digest(candidate),
        max_abs=max(distances) if both else None,
        mean_abs=math.fsum(distances) / vocab if both else None,
        rmse=math.sqrt(math.fsum(d * d for d in distances) / vocab) if both else None,
    )


def bounded(path, limit):
    require(path.is_file() and not path.is_symlink(), "missing or linked evidence: " + path.name)
    with path.open("rb") as f:
        data = f.read(limit + 1)
    require(0 < len(data) <= limit, "empty or oversized evidence: " + path.name)
    return data


def sealed(r, raw, name, limit):
    data = bounded(raw / name, limit)
    require(r["raw_sha256"][name] == digest(data), "changed raw evidence: " + name)
    return data


def validate_http(r, raw):
    request = sealed(r, raw, "request.json", 65536)
    response = sealed(r, raw, "response.json", 1048576)
    req = json.loads(request)
    reply = json.loads(response)
    http = r["after_ready"]
    require(
        http["http_status"] == 200
        and digest(request) == r["request_sha256"] == http["request_sha256"]
        and digest(response) == http["response_sha256"],
        "HTTP event or bytes",
    )
    prompt = req["prompt"]
    require(
        isinstance(prompt, list)
        and len(prompt) == 16
        and all(type(t) is int and 0 <= t < VOCAB for t in prompt)
        and digest(struct.pack("<16i", *prompt)) == r["prompt_ids_sha256"],
        "prompt identity",
    )
    require(
        req["n_predict"] == 1
        and req["temperature"] == 0
        and req["seed"] == 42
        and req["id_slot"] == 0
        and req.get("n_probs", 0) == 0
        and req.get("stream", False) is False
        and req["return_tokens"] is True,
        "sampling contract",
    )
    fields = {
        "cache_n": 0,
        "prompt_n": 16,
        "predicted_n": 1,
        "tokens_evaluated": 16,
        "tokens_predicted": 1,
        "id_slot": 0,
    }
    for k, val in fields.items():
        source = reply["timings"] if k in ("cache_n", "prompt_n", "predicted_n") else reply
        require(
            type(http[k]) is int and type(source[k]) is int and http[k] == source[k] == val,
            "response field " + k,
        )
    require(
        reply["stop"] is True
        and reply["truncated"] is False
        and reply["tokens"] == [r["sampled_id"]]
        and type(reply["tokens"][0]) is int
        and 0 <= r["sampled_id"] < VOCAB
        and r["sampled_id"] == http["sampled_id"],
        "response token or terminal state",
    )


def verified_row(report_dir, raw_parent):
    r = json.loads(bounded(Path(report_dir) / "receipt.json", 1048576))
    raw = Path(raw_parent) / "raw"
    require(
        r["status"] == "PASS_STOCK_SERVER_RAW_LOGITS_ARM"
        and r["child_gone"] is True
        and type(r["returncode"]) is int
        and r["returncode"] == 0
        and r["server_starts"] == r["http_requests_sent"] == r["sampling_tokens_requested"] == 1,
        "unclean/incomplete arm",
    )
    mode = r["arm"]
    require(
        mode in ARMS and r["cap_bytes"] == (20 if mode == "B20" else 10) * 2**30, "arm or envelope"
    )
    require(
        r["server_sha256"] == SERVER
        and r["active_libllama_sha256"] == (STOCK if mode == "S" else CAND)
        and re.fullmatch("[0-9a-f]{64}", r["observer_sha256"]),
        "server/loader/observer identity",
    )
    require(r["row_file"] == "row.f32", "capture filename")
    row = sealed(r, raw, "row.f32", VOCAB * 4)
    capture = json.loads(sealed(r, raw, "capture.json", 65536))
    validate_http(r, raw)
    require(
        capture["status"] == "PASS"
        and capture["reason"] == ""
        and capture["profile"] == "stock120b"
        and capture["armed_calls"] == 1
        and capture["row_index"] == 15
        and capture["n_vocab"] == VOCAB
        and capture["row_bytes"] == len(row) == VOCAB * 4
        and capture["caller_sha256"] == CALLER
        and capture["caller_offset"] in (0x26951F, 0x269A6D)
        and capture["provider_sha256"] == r["active_libllama_sha256"]
        and capture["row_sha256"] == r["row_sha256"] == digest(row),
        "unqualified capture",
    )
    vals = struct.unpack(f"<{VOCAB}f", row)
    require(all(map(math.isfinite, vals)), "nonfinite row")
    require(
        max(range(VOCAB), key=vals.__getitem__)
        == capture["argmax"]
        == r["greedy_id"]
        == r["sampled_id"],
        "argmax/response mismatch",
    )
    return r, row


def compare_family(pairs, *, expected_prompt_sha256=None):
    result = {"status": "FAIL_PRESERVED", "arms": [], "not_run": []}
    idx = 0
    try:
        require(1 <= len(pairs) <= len(ARMS), "one to four ordered arms")
        ref = None
        for idx, (report, raw) in enumerate(pairs):
            r, data = verified_row(report, raw)
            require(r["arm"] == ARMS[idx], "unexpected arm order")
            require(
                expected_prompt_sha256 is None or r["prompt_ids_sha256"] == expected_prompt_sha256,
                "input differs from C110",
            )
            if ref is None:
                ref, base = r, data
            same = (
                "request_sha256",
                "prompt_ids_sha256",
                "observer_sha256",
                "server_sha256",
                "measurement_commit",
                "measurement_tree",
            )
            require(all(r[k] == ref[k] for k in same), "noncomparable requests or binaries")
            comparison = summarize(base, data)
            result["arms"].append(
                {
                    "arm": r["arm"],
                    "receipt_sha256": digest((Path(report) / "receipt.json").read_bytes()),
                    "cap_bytes": r["cap_bytes"],
                    "sampled_id": r["sampled_id"],
                    "request_sha256": r["request_sha256"],
                    "prompt_ids_sha256": r["prompt_ids_sha256"],
                    **comparison,
                }
            )
            require(comparison["bitwise_equal"], "raw F32 differs from independent stock")
        result["status"] = {3: "PASS_E10_BITWISE", 4: "PASS_E10_AND_E20_TRANSFER_BITWISE"}.get(
            len(pairs), "PASS_PREFIX"
        )
        result["not_run"] = list(ARMS[len(pairs) :])
    except (OSError, ValueError, TypeError, KeyError, IndexError) as e:
        result.update(error=str(e), failed_arm=ARMS[min(idx, 3)], not_run=list(ARMS[idx + 1 :]))
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--arm",
        nargs=2,
        action="append",
        required=True,
        metavar=("REPORT_DIR", "RAW_PARENT"),
        type=Path,
    )
    cli.add_argument("--c110-raw", required=True, type=Path)
    cli.add_argument("--new-output-dir", required=True, type=Path)
    a = cli.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        _, meta = load_prompt(a.c110_raw)
        result = compare_family(a.arm, expected_prompt_sha256=meta["prompt_ids_sha256"])
        result["inputs"] = meta
    except (OSError, ValueError, KeyError, TypeError) as e:
        result = {"status": "FAIL_PRESERVED", "error": str(e), "not_run": list(ARMS)}
    result["program_sha256"] = digest(Path(__file__).read_bytes())
    result["physical_protocol_sha256"] = digest(
        (Path(__file__).parent / "physical-protocol.md").read_bytes()
    )
    pending = a.new_output_dir / "receipt.pending"
    with pending.open("x") as f:
        f.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    pending.rename(a.new_output_dir / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
