"""Bind the two physical source paths before replaying the archived bank grader."""

import hashlib
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE.parents[2] / "client/grade.py"))
need = G["need"]
CAP = 1 << 20


def maps(path):
    result = []
    for line in path.read_text().splitlines():
        span, perm, offset, dev, ino, *name = line.split(maxsplit=5)
        lo, hi = (int(x, 16) for x in span.split("-"))
        result.append((lo, hi, perm, int(offset, 16), dev, int(ino), name))
    return result


def region(vmas, address, size):
    hits = [v for v in vmas if v[0] <= address < address + size <= v[1]]
    need(len(hits) == 1, "physical source VMA")
    return hits[0]


def schedule(raw):
    # Triples of sources/destinations and the actual physical ranks at consumers.
    sets = [
        (r[0], r[4], r[6], r[7], r[9])
        for r in G["records"](raw, "SET")
        if r[4].startswith("moe_cache.") and r[4].endswith("_exps.weight")
    ]
    nodes = [(r[0], r[2], r[3], r[-1]) for r in G["records"](raw, "NODE")]
    return sets, nodes


def audit(
    raw,
    mode,
    native,
    model,
    *,
    sites=None,
    capacity=CAP,
    weight_slice=None,
    vma_files=None,
    expected_bytes=None,
    reference_routes=None,
):
    need(mode in ("DIRECT", "PREAD_RANDOM"), "bank arm")
    ranges = mode == "PREAD_RANDOM"
    if sites is None:
        sites = [(3, 0, 512), (3, 1, 512), (4, 0, 16), (4, 1, 16)]
    weight_slice = weight_slice or G["weight_slice"]
    vmas = {p: maps(native / f) for p, f in (vma_files or {3: "maps", 4: "maps"}).items()}
    expected_bytes = expected_bytes or {3: 1044480, 4: 104448}
    stat = model.stat()
    sets, sources, copied, physical_h2d = {}, {}, {}, []
    phase_bytes = {3: 0, 4: 0}
    gets, fences, routes = [], [], {}
    backend = arena = awaiting = None
    generation = pending = cursor = peak = 0
    ended = False
    result = []
    for line in raw.splitlines():
        w = line.split()
        if not w:
            continue
        tag = w[0]
        if tag == "ROUTE":
            key = int(w[1]), int(w[2].rsplit("-", 1)[1])
            need(
                key not in routes and (reference_routes is None or reference_routes[key] == w[3]),
                "unexpected router IDs",
            )
            routes[key] = w[3]
        elif tag == "BANK_GET":
            phase, gen, b, pc, n = map(int, w[1:])
            need(
                not ended
                and len(gets) == len(fences)
                and gen == generation + 1 <= len(sites)
                and phase == sites[gen - 1][0]
                and pc > 0
                and n == sites[gen - 1][2]
                and b > 0
                and backend in (None, b),
                "ID get",
            )
            backend = b
            gets.append((phase, gen, b, pc))
        elif tag == "BANK_FENCE":
            phase, gen, b, pc, count = map(int, w[1:6])
            need(
                len(w) == 7
                and len(gets) == len(fences) + 1
                and (phase, gen, b) == gets[-1][:3]
                and gen == generation + 1
                and pc > 0
                and count == pending
                and (routes if reference_routes is None else reference_routes).get(
                    tuple(sites[gen - 1][:2])
                )
                == w[6],
                "synchronized ordered ID values or outstanding SETs",
            )
            fences.append(pc)
            generation, pending, cursor = gen, 0, 0
        elif tag == "SET" and w[5].startswith("moe_cache.") and w[5].endswith("_exps.weight"):
            phase, ticket, parent = map(int, w[1:4])
            need(
                phase in phase_bytes
                and ticket not in sets
                and parent == 0
                and w[4] == "async"
                and awaiting is None
                and not ended,
                "original bank SET",
            )
            sets[ticket] = (phase, *map(int, w[6:]))
            awaiting = ticket
        elif tag == "BANK_SOURCE":
            phase, ticket, gen, b, layer, orig, off, eff, effoff, n = map(int, w[1:])
            need(
                ticket in sets and ticket == awaiting and ticket not in sources,
                "source owner/order",
            )
            p, dst, destoff, size, original, file = sets[ticket]
            sliced = weight_slice(off, n)
            need(
                (phase, orig, off, n) == (p, original, file, size)
                and sliced
                and 1 <= gen <= len(sites)
                and sliced[0][0] == layer == sites[gen - 1][1]
                and gen == generation
                and len(fences) == len(gets) == gen
                and b == backend,
                "source identity",
            )
            v = region(vmas[phase], orig, n)
            device = tuple(int(x, 16) for x in v[4].split(":"))
            need(
                v[2].startswith("r-")
                and v[5] == stat.st_ino
                and v[6] == [str(model)]
                and device == (os.major(stat.st_dev), os.minor(stat.st_dev))
                and v[3] + orig - v[0] == off,
                "original GGUF VMA",
            )
            head = cursor + off % 4096
            if ranges:
                v = region(vmas[phase], eff, n)
                need(
                    effoff == -1
                    and eff != orig
                    and v[2] == "rw-p"
                    and v[4:6] == ("00:00", 0)
                    and not v[6],
                    "explicit read must use anonymous scratch",
                )
                if arena is None:
                    arena = eff - head
                    need(arena > 0 and not arena % 4096, "scratch alignment")
                need(eff == arena + head, "overlap or scratch reuse before fence")
            else:
                need((eff, effoff) == (orig, off), "direct must use GGUF address")
            cursor = ((head + n + 4095) // 4096) * 4096
            peak = max(peak, cursor)
            need(peak <= capacity, "scratch capacity")
            sources[ticket] = (phase, gen, orig, off, eff, effoff, dst + destoff, n)
            copied[ticket] = []
            phase_bytes[phase] += n
            pending += 1
            awaiting = None
        elif tag == "COPY" and int(w[4]) in (1, 4) and int(w[7]):
            phase, ticket = map(int, w[1:3])
            dst, src, n, off, rc = map(int, w[5:])
            physical_h2d.append((src, n, ticket in sources))
            if ticket in sets:
                need(ticket in sources and not ended, "physical copy before source or after drain")
                p, gen, orig, file, eff, effoff, base, size = sources[ticket]
                rel = src - eff
                need(
                    phase == p
                    and gen == generation
                    and 0 <= rel < rel + n <= size
                    and w[3] == "async"
                    and w[4] == "1"
                    and rc == 0
                    and dst == base + rel
                    and off == (-1 if ranges else effoff + rel),
                    "physical CUDA transfer",
                )
                copied[ticket].append((rel, n))
                # Supply logical GGUF coordinates to the historical verifier in memory only.
                w[6], w[8] = str(orig + rel), str(file + rel)
                line = " ".join(w)
        elif tag == "BANK_END":
            need(
                not ended
                and list(map(int, w[1:])) == [generation, pending]
                and generation == len(sites)
                and len(gets) == len(fences) == len(sites),
                "cleanup",
            )
            ended = True
        elif tag.startswith("BANK_"):
            raise ValueError("unknown source journal record")
        elif tag == "STATUS":
            need(ended, "client completed before source teardown")
        result.append(line)
    need(
        ended
        and len(set(x[3] for x in gets)) == len(set(fences)) == 1
        and gets[0][3] != fences[0]
        and awaiting is None
        and set(sets) == set(sources),
        "incomplete bank events",
    )
    for ticket, spans in copied.items():
        G["coverage"](spans, sources[ticket][-1])
    if ranges:
        need(
            arena is not None
            and all(
                bound
                for src, n, bound in physical_h2d
                if src < arena + capacity and arena < src + n
            ),
            "unbound H2D from scratch",
        )
    need(phase_bytes == expected_bytes, "payload conservation")
    summary = dict(
        source=mode,
        bank_sets=len(sets),
        physical_copies=sum(map(len, copied.values())),
        phase_bytes=phase_bytes,
        scratch_reserved_B=capacity,
        scratch_high_water_B=peak,
        id_fences=len(fences),
        fills_at_cleanup=pending,
        raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
    )
    return "\n".join(result) + "\n", summary
