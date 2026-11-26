"""Decode a TPR1 diagnostic journal, yielding authoritative ordered groups and cuts."""

import argparse
import hashlib
import json
from pathlib import Path


def require(condition):
    if not condition:
        raise ValueError("incomplete or invalid prefix-route journal")


def records(raw):
    require(len(raw) <= 1024**2 and raw.startswith(b"TPR1"))
    at = 4

    def take(n):
        nonlocal at
        require(at + n <= len(raw))
        v = raw[at : at + n]
        at += n
        return v

    def u16():
        return int.from_bytes(take(2), "little")

    def one():
        return take(1)[0]

    call = ub = consumed = cap = next_pos = layer = phase = 0
    prefix_call = incremental_call = 0
    mode = "between"
    while at < len(raw):
        tag = take(1)
        if tag == b"C":
            require(mode == "between")
            serial, cap = u16(), u16()
            require(serial == call + 1 and 1 <= cap <= 256)
            call, ub, consumed, mode = serial, 0, 0, "call"
        elif tag == b"U":
            require(mode == "call")
            serial, n = u16(), one()
            require(serial == ub + 1 and 1 <= n <= 32 and n + consumed <= cap)
            positions = []
            outputs = []
            for _ in range(n):
                pos, flag = u16(), one()
                require(pos == next_pos < 8192 and flag in (0, 1))
                positions.append(pos)
                if flag:
                    outputs.append(pos)
                next_pos += 1
            ub, consumed, layer, mode = serial, consumed + n, 0, "ubatch"
        elif tag == b"R":
            require(mode == "ubatch" and layer < 36)
            index, path, n = one(), take(1), one()
            selected = outputs if layer == 35 else positions
            require(index == layer and path in (b"S", b"M") and n == len(selected) > 0)
            for pos in selected:
                ids = tuple(take(4))
                require(len(set(ids)) == 4 and max(ids) < 128)
                yield "row", call, ub, layer, pos, path.decode(), ids
            layer += 1
        elif tag == b"Z":
            require(mode == "ubatch" and layer == 35 and not outputs)
            yield "pruned", call, ub, layer
            layer += 1
        elif tag == b"E":
            require(mode == "ubatch" and layer == 36)
            mode = "call"
        elif tag == b"D":
            require(mode == "call" and consumed == cap)
            mode = "between"
        elif tag in (b"P", b"I"):
            require(
                mode == "between"
                and call > 0
                and (tag, phase) in [(b"P", 0), (b"I", 1)]
                and (phase == 0 or call > prefix_call)
            )
            if phase == 0:
                prefix_call = call
            else:
                incremental_call = call
            phase += 1
            yield "cut", tag.decode(), call
        elif tag == b"F":
            require(mode == "between" and phase == 2 and call > incremental_call and at == len(raw))
            return
        else:
            require(False)
    raise ValueError("missing terminal record")


def summarize(raw):
    counts = [[0] * 128 for _ in range(36)]
    rows = pruned = 0
    cuts = {}
    for item in records(raw):
        if item[0] == "row":
            rows += 1
            for expert in item[-1]:
                counts[item[3]][expert] += 1
        elif item[0] == "pruned":
            pruned += 1
        else:
            encoded = json.dumps(counts, separators=(",", ":")).encode()
            cuts[item[1]] = {
                "call": item[2],
                "logical_rows_so_far": rows,
                "per_layer_expert_count_sha256": hashlib.sha256(encoded).hexdigest(),
            }
    return {
        "status": "COMPLETE_JOURNAL",
        "rows": rows,
        "pruned_groups": pruned,
        "cuts": cuts,
        "journal_bytes": len(raw),
        "journal_sha256": hashlib.sha256(raw).hexdigest(),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("journal", type=Path)
    a = p.parse_args()
    with a.journal.open("rb") as stream:
        result = summarize(stream.read(1024**2 + 1))
    print(json.dumps(result, indent=2, sort_keys=True))
