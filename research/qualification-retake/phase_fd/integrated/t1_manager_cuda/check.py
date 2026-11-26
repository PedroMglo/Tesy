"""Portable witness checks. No model, GGML, compiler, CUDA or host access."""

import hashlib
import math
import struct

ARMS = ("old", "new", "original", "event", "broken")
WIDTH = 32
ROLES = 3
SLOTS = 4


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(test, reason):
    if not test:
        raise ValueError(reason)


def component(generation, role, slot):
    exponent = 118 + generation + role + int(slot > 0)
    return (bytes([exponent]) + b"\x22" * 16) * WIDTH


def scalar(generation):
    # Nibble 2 represents +1. Matrix rows are constant and all activations equal 1/4.
    gate, down, up = (2.0 ** (118 + generation + r - 127) for r in range(ROLES))
    x, y = WIDTH * 0.25 * gate, WIDTH * 0.25 * up
    return WIDTH * down * (y + 1) * x / (1 + math.exp(-1.702 * x))


def verify_arm(arm, slots, bank, out, token, journal, old, new):
    require(arm in ARMS and len(out) == 4 * WIDTH, "arm and output width")
    seengen = 2 if arm in ("new", "broken") else 1
    expected = new if seengen == 2 else old
    require(old != new and out == expected, "complete old/new FFN output")
    values = struct.unpack("<32f", out)
    error = max(abs(v - scalar(seengen)) for v in values)
    require(all(math.isfinite(v) for v in values) and error <= 0.0001, "independent scalar gold")
    expected_slots = b"".join(
        component(2 if slot == 0 and arm != "old" else 1, role, slot)
        for role in range(ROLES)
        for slot in range(SLOTS)
    )
    require(slots == expected_slots, "all components including parking")
    gold = arm in ("old", "new")
    expected_bank = None if gold else b"".join(component(1, role, 0) for role in range(ROLES))
    require(bank == expected_bank, "three captured old roles")
    require(token == (old[:4] if arm == "original" else None), "original ordering token")
    names = ["READER_RELEASED", "GRAPH_DONE"]
    if not gold:
        names += ["CAPTURED", "OVERWRITTEN", "OBSERVER"]
    require(sorted(journal) == sorted(names), "event coverage")
    edges = [("READER_RELEASED", "GRAPH_DONE")]
    if not gold:
        edges += [("CAPTURED", "OVERWRITTEN")]
    if arm == "original":
        edges += [
            ("CAPTURED", "READER_RELEASED"),
            ("READER_RELEASED", "OBSERVER"),
            ("OBSERVER", "OVERWRITTEN"),
            ("OBSERVER", "GRAPH_DONE"),
        ]
    if arm == "event":
        edges += [("CAPTURED", "READER_RELEASED"), ("GRAPH_DONE", "OVERWRITTEN")]
    if arm == "broken":
        edges += [("OBSERVER", "OVERWRITTEN"), ("OVERWRITTEN", "READER_RELEASED")]
    require(all(journal.index(a) < journal.index(b) for a, b in edges), "ordering evidence")
    return dict(
        complete_output_sha256=digest(out),
        primary_sha256=digest(slots),
        capture_sha256=digest(bank) if bank else None,
        journal=journal,
        max_abs_error_independent=error,
        values=WIDTH,
    )
