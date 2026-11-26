"""Check matrix traffic through SET and CUDART without using a graph-evaluation callback."""

import hashlib
import json
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE.parent / "grade.py"))
need = G["need"]
ROLES, SLAB = G["ROLES"], G["SLAB"]
BANK_NAME = re.compile(r"moe_cache\.blk\.0\.ffn_(gate|up|down)_exps\.weight")
FILE_NAME = re.compile(r"blk\.(\d+)\.ffn_(gate|up|down)_exps\.weight")
PHASE = {"prefill": 3, "teacher": 4}


def expected(ledger):
    return sorted(
        (PHASE[r["phase"]], r["layer"], role, expert, slot)
        for r in ledger
        for expert, slot in r["fills"]
        for role in ROLES
    )


def fills(lines, plan, slots):
    """Reconcile relative slot, original GGUF extent and nested copies at each SET ticket."""
    spans = []
    for name, (off, size, _) in plan.items():
        name_match = FILE_NAME.fullmatch(name)
        if name_match:
            need(size == 128 * SLAB, "matrix extent")
            spans.append((off, off + size, int(name_match[1]), name_match[2]))
    spans.sort()
    starts = [s[0] for s in spans]
    need(spans and all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False)), "overlap")

    def intersects(off, size):
        i = bisect_right(starts, off + size - 1) - 1
        return spans[i] if off >= 0 and size > 0 and i >= 0 and off < spans[i][1] else None

    # A write can precede the first named SET for that bank. Recover the addresses
    # first, then verify every forward write in its original chronological order.
    addresses = {}
    for line in lines:
        if line.startswith(("SET 3 ", "SET 4 ")):
            _, _, _, _, _, name, base, *_ = line.split()
            match = BANK_NAME.fullmatch(name)
            if match:
                addr, role = int(base), match[1]
                need(addr > 0 and addresses.setdefault(role, addr) == addr, "bank moved")
    tickets, copies, events = {}, defaultdict(list), []
    all_sets = set()
    # Keep the observed order. The owner must exist before its first CUDA copy.
    for line in lines:
        v = line.split()
        if len(v) < 2 or v[1] not in ("3", "4"):
            continue
        phase = int(v[1])
        if v[0] == "SET":
            _, _, key, _, api, name, base, off, size, src, fo = v
            need(key not in all_sets and api in ("sync", "async"), "SET ticket")
            all_sets.add(key)
            match = BANK_NAME.fullmatch(name)
            if not match:
                continue
            addr, off, size, src, fo = map(int, (base, off, size, src, fo))
            span = intersects(fo, size)
            need(span and span[0] <= fo < fo + size <= span[1] and match[1] == span[3], "file role")
            start, _, layer, role = span
            need(0 <= off < off + size <= slots * SLAB, "slot bounds")
            need((fo - start) % SLAB == off % SLAB == size % SLAB == 0, "partial expert")
            tickets[key] = phase, addr + off, size, src, fo
            for i in range(size // SLAB):
                events.append((phase, layer, role, (fo - start) // SLAB + i, off // SLAB + i))
        elif v[0] == "COPY":
            _, _, key, api, kind, dst, src, size, fo, rc = v
            kind, dst, src, size, fo = map(int, (kind, dst, src, size, fo))
            need(
                api in ("sync", "async", "sync2d", "async2d")
                and int(rc) == 0
                and kind in range(4)
                and size >= 0,
                "failed or unknown copy",
            )
            if key not in tickets:
                need(not (kind == 1 and intersects(fo, size)), "unowned matrix copy")
                need(
                    not (
                        kind in (1, 3)
                        and size
                        and any(
                            dst < base + slots * SLAB and dst + size > base
                            for base in addresses.values()
                        )
                    ),
                    "unowned bank write",
                )
                continue
            p, target, total, origin, file_start = tickets[key]
            delta = dst - target
            need(
                p == phase
                and kind == 1
                and 0 <= delta < delta + size <= total
                and src - origin == fo - file_start == delta,
                "CUDA copy origin or slot",
            )
            copies[key].append((delta, size))
        elif v[0] in ("REG", "PEER"):
            raise ValueError("unexpected registration or peer copy")
        elif v[0] == "MEMSET":
            _, _, api, dst, _, size, rc = v
            dst, size = int(dst), int(size)
            need(api in ("sync", "async") and int(rc) == 0 and size >= 0, "failed memset")
            need(
                not (
                    size
                    and any(dst < b + slots * SLAB and dst + size > b for b in addresses.values())
                ),
                "matrix bank memset",
            )
    need(set(addresses) == set(ROLES), "missing bank")
    bases = sorted(addresses.values())
    need(
        all(a + (slots + 1) * SLAB <= b for a, b in zip(bases, bases[1:], strict=False)),
        "bank overlap",
    )
    for key, (_, _, size, _, _) in tickets.items():
        G["TINY"]["coverage"](copies[key], size)
    return sorted(events)


def fingerprint(events):
    return hashlib.sha256(json.dumps(events, separators=(",", ":")).encode()).hexdigest()


def compare(lines, plan, slots, ledger):
    a, b = expected(ledger), fills(lines, plan, slots)
    ca, cb = Counter(a), Counter(b)
    return dict(
        match=a == b,
        expected_sha256=fingerprint(a),
        observed_sha256=fingerprint(b),
        missing_slices=sum((ca - cb).values()),
        extra_slices=sum((cb - ca).values()),
        first_missing=next(iter(sorted(ca - cb)), None),
        first_extra=next(iter(sorted(cb - ca)), None),
        matrix_requests_B={
            name: SLAB * sum(n for row, n in cb.items() if row[0] == phase)
            for name, phase in PHASE.items()
        },
    )
