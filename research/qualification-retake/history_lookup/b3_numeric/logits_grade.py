"""Compare complete 201088-entry C269 F32 rows, without disclosing token IDs."""

import hashlib
import math
import struct
from pathlib import Path

N_VOCAB = 201_088
ROW_BYTES = 4 * N_VOCAB


def _row(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size != ROW_BYTES:
        raise ValueError("expected one complete, regular F32 logits row")
    data = path.read_bytes()
    if len(data) != ROW_BYTES:
        raise ValueError("logits size changed while reading")
    values = struct.unpack(f"<{N_VOCAB}f", data)
    if not all(map(math.isfinite, values)):
        raise ValueError("non-finite logits")
    return data, values


def compare_rows(ref: Path, cand: Path):
    left, a = _row(ref)
    right, b = _row(cand)
    max_a, max_b = max(a), max(b)
    ties_a, ties_b = a.count(max_a), b.count(max_b)
    first_argmax_equal = a.index(max_a) == b.index(max_b)
    # Equality of floats treats positive and negative zero as equal; the bytes distinguish them.
    bits_a = struct.iter_unpack("<I", left)
    bits_b = struct.iter_unpack("<I", right)
    deltas = [x - y for x, y in zip(a, b, strict=True)]
    return {
        "n_vocab": N_VOCAB,
        "reference_sha256": hashlib.sha256(left).hexdigest(),
        "candidate_sha256": hashlib.sha256(right).hexdigest(),
        "finite": True,
        "bitwise": left == right,
        "changed_f32_bit_patterns": sum(x != y for x, y in zip(bits_a, bits_b, strict=True)),
        "changed_values": sum(delta != 0 for delta in deltas),
        "same_greedy": ties_a == ties_b == 1 and first_argmax_equal,
        "same_first_argmax": first_argmax_equal,
        "same_max_set": all((x == max_a) == (y == max_b) for x, y in zip(a, b, strict=True)),
        "reference_max_ties": ties_a,
        "candidate_max_ties": ties_b,
        "max_abs": max(abs(delta) for delta in deltas),
        "rmse": math.sqrt(math.fsum(delta * delta for delta in deltas) / N_VOCAB),
    }
