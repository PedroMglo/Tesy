"""Freeze causal R0 frequency tables at P and I from a completely validated TPR1."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UNIT))
from causal_prefix import top40  # noqa: E402
from prefix_observer.journal import records  # noqa: E402


def freeze_tables(journal, prefix_calls, prefix_tokens, increment_tokens, decode_steps):
    """Read past I only to validate coverage. Decode rows cannot change either table."""
    scores = [[0] * 128 for _ in range(36)]
    snapshots = {}
    phase_rows = [[0] * 36 for _ in range(3)]
    for entry in records(journal):
        phase = len(snapshots)
        if entry[0] == "cut":
            name, call = entry[1:]
            if (name, call) != (("P", prefix_calls), ("I", prefix_calls + 1))[phase]:
                raise ValueError("incorrect causal cut")
            snapshots[name] = [row.copy() for row in scores]
        elif entry[0] == "row":
            _, call, _, layer, position, _, ids = entry
            first = (0, prefix_tokens, prefix_tokens + increment_tokens)[phase]
            width = (prefix_tokens, increment_tokens, decode_steps)[phase]
            if not first <= position < first + width:
                raise ValueError("route in wrong phase")
            if phase == 2 and call != prefix_calls + 2 + position - first:
                raise ValueError("decode call and position disagree")
            phase_rows[phase][layer] += 1
            if phase < 2:
                for expert in ids:
                    scores[layer][expert] += 1
    expected = [
        [prefix_tokens] * 35 + [prefix_calls],
        [increment_tokens] * 35 + [1],
        [decode_steps] * 36,
    ]
    if phase_rows != expected or set(snapshots) != {"P", "I"}:
        raise ValueError("incomplete target route coverage")
    return snapshots


def describe(table):
    layers = []
    for layer, row in enumerate(table):
        ranked = top40(row)
        frequencies = Counter(row)
        cutoff = row[ranked[-1]]
        layers.append(
            {
                "layer": layer,
                "votes": sum(row),
                "zero_scores": frequencies[0],
                "experts_tied_with_another": sum(n for n in frequencies.values() if n > 1),
                "tie_at_cutoff": frequencies[cutoff],
                "top40_by_score_then_id": ranked,
            }
        )
    data = json.dumps(table, separators=(",", ":")).encode()
    return {"counts_sha256": hashlib.sha256(data).hexdigest(), "layers": layers}
