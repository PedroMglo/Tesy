"""Compare the exact order of each single-row C294 top-k with its sealed decode reference."""

import argparse
import hashlib
import json
import math
import resource
import signal
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cache_boundary as boundary  # noqa: E402

SHA = {
    "nominal153": "62ff2da0c33e77847aaa56e4c802c2a4569fcd5f08d971b9bda04a0a4c65e17c",
    "code153": "2045b1c9510432fb0f98d4941db07b3f5472ffa4e9adb0c8f45ad547089dcb2c",
}
PROMPT = {"nominal153": 2197, "code153": 2105}
PROTOCOL = "ac8c25f5a38313e75d4fbb25ba15908be16a350e733582e46ef11eb17b6b2c6e"


def check_witness(case, groups):
    """Rows are (decode call 1..32, layer, absolute position, ordered four expert IDs)."""
    data = bytearray()
    n = 0
    for n, (call, layer, position, ids) in enumerate(groups, 1):
        want_call, want_layer = divmod(n - 1, 36)
        boundary.require(
            type(call) is type(layer) is type(position) is int
            and n <= 1152
            and (call, layer, position) == (want_call + 1, want_layer, PROMPT[case] + want_call),
            "missing or misplaced decode row",
        )
        ids = tuple(ids)
        boundary.require(
            len(ids) == len(set(ids)) == 4 and all(type(x) is int and 0 <= x < 128 for x in ids),
            "invalid top-k",
        )
        data.extend(ids)
    digest = hashlib.sha256(data).hexdigest()
    boundary.require(n == 1152 and digest == SHA[case], "ordered decode reference mismatch")
    return digest


def geometry(d, case):
    count = PROMPT[case]
    plan = [256] * 7 + [count - 153 - 7 * 256, 153]
    boundary.require(
        d["trace"] is True
        and d["profile"] == "R0"
        and d["case"] == case
        and d["external_prefill_calls"] == plan
        and len(d["official_input_ids"]) == count
        and d["decode_calls"] == len(d["teacher_forced_ids"]) == 32
        and len(d["native_argmax_ids"]) == d["output_rows"] == 33
        and d["decode_positions"] == [count, count + 31]
        and d["FFN_last_layer_rows_per_call"] == 1
        and d["numerical_FFN_tiles"] == [32, 32, 32, 32, 25],
        "initial or incremental geometry changed",
    )
    physical = plan + [1] * 32
    calls = len(physical)
    ubatches = sum((n + 31) // 32 for n in physical)
    groups = 35 * sum(physical) + calls
    records = 35 * ubatches + calls
    return {
        "calls": calls,
        "ubatches": ubatches,
        "layer35_output_rows": calls,
        "layer35_pruned_ubatches": ubatches - calls,
        "expected_groups": groups,
        "expected_tpr1_bytes": 4
        + 6 * calls
        + 4 * ubatches
        + 3 * sum(physical)
        + 4 * records
        + 4 * groups
        + (ubatches - calls)
        + ubatches
        + 3,
    }


def witness_rows(path, case, expected_sha):
    """Only the ordered router/select rows must survive the full generation/state replay."""
    ordered = []
    current = None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        header = next(stream)
        digest.update(header)
        boundary.require(header.decode().strip() == boundary.HEADER, "C294 schema")
        for line in stream:
            digest.update(line)
            kind, _, call, route, layer, expert, _, _, _, _, rows = map(int, line.split())
            if call < 1 or kind not in (2, 3):
                continue
            key = (call, layer, route)
            if kind == 2:
                if current is not None:
                    boundary.require(len(ordered[-1][3]) == 4, "missing previous ranks")
                boundary.require(rows == 1 and route > 0, "multirow in decode")
                current = key
                ordered.append((call, layer, PROMPT[case] + call - 1, []))
            else:
                boundary.require(key == current, "select not linked to its route")
                ordered[-1][3].append(expert)
    boundary.require(digest.hexdigest() == expected_sha, "journal changed during stream")
    return ordered


def test_swap(case, groups):
    # Exchange ranks of the same real cohort, preserving its unordered content.
    first, *rest = groups
    call, layer, pos, ids = first
    wrong = [ids[1], ids[0], ids[2], ids[3]]
    boundary.require(set(wrong) == set(ids) and wrong != ids, "ineffective mutation")
    for mutant in [
        [(call, layer, pos, wrong), *rest],
        [(call, layer, pos + 1, ids), *rest],
        groups[:-1],
    ]:
        try:
            check_witness(case, mutant)
        except ValueError:
            continue
        raise ValueError("reference accepted a wrong witness")


def audit(raw):
    def verified_json(path, digest):
        b = path.read_bytes()
        boundary.require(hashlib.sha256(b).hexdigest() == digest, "changed reference input")
        return json.loads(b)

    m = verified_json(boundary.MANIFEST, boundary.MANIFEST_SHA)
    entries = {f["path"]: f for f in m["files"]}
    p = verified_json(boundary.MANIFEST.parent / "protocol.json", PROTOCOL)
    arms = {}
    for name in boundary.NAMES:
        case = name.split("-")[1]
        _, slot = boundary.audit_arm(raw, name)
        base = raw / (name + ".native")
        d = verified_json(base / "result.json", slot["source_sha256"]["result.json"])
        groups = witness_rows(base / "events.tsv", case, slot["source_sha256"]["events.tsv"])
        ids = check_witness(case, groups)
        test_swap(case, groups)
        logits = base / "all33.logits.f32"
        e = entries[
            str(Path("results") / boundary.CAMPAIGN / "raw" / (name + ".native") / logits.name)
        ]
        size = 33 * 201088 * 4
        boundary.require(logits.stat().st_size == e["bytes"] == size, "full-row length mismatch")
        dig = hashlib.sha256()
        with logits.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                dig.update(chunk)
                boundary.require(
                    all(math.isfinite(x) for (x,) in struct.iter_unpack("<f", chunk)),
                    "nonfinite reference",
                )
        boundary.require(
            dig.hexdigest() == e["sha256"] == p["expected_full_logits_sha256"][case],
            "changed full-row anchor",
        )
        arms[name] = {
            "ordered_decode_sha256": ids,
            "decode_groups": len(groups),
            "decode_selections": 4 * len(groups),
            "source_sha256": {**slot["source_sha256"], logits.name: dig.hexdigest()},
            "finite_logit_rows": 33,
            "planned_geometry": geometry(d, case),
            "negative_checks": ["rank_swap", "wrong_position", "missing_last_group"],
        }
    return arms


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir()
    cap = 256 * 1024**2
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    start = time.monotonic()
    signal.signal(signal.SIGALRM, boundary.deadline)
    signal.alarm(60)
    result = {
        "status": "FAIL_PRESERVED",
        "forwards": 0,
        "physical_weight_bytes": 0,
        "raw_manifest_sha256": boundary.MANIFEST_SHA,
        "protocol_sha256": PROTOCOL,
        "sources_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (HERE / "protocol.md", HERE / "repair.md", Path(__file__))
        },
    }
    try:
        result["arms"] = audit(a.raw_dir)
        result["status"] = "PASS_HISTORICAL_ORDERED_DECODE"
    except FileNotFoundError:
        result["status"] = "NOT_RUN_RAW_REQUIRED"
    except (OSError, KeyError, ValueError, StopIteration, MemoryError) as exc:
        result["error"] = type(exc).__name__
    finally:
        signal.alarm(0)
    result.update(
        wall_s=round(time.monotonic() - start, 3),
        maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    if result["maxrss_kib"] > 256 * 1024 or result["wall_s"] > 60:
        result["status"] = "FAIL_BUDGET"
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
    print(result["status"])
    raise SystemExit(int(result["status"] != "PASS_HISTORICAL_ORDERED_DECODE"))
