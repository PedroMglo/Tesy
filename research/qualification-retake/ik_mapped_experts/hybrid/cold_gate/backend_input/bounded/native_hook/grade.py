"""Bind native routing, storage lifetimes and the actual CUDART copies before numerical grading."""

from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
TINY = HERE.parents[1] / "tiny_graph"
R = run_path(str(TINY / "review.py"))
A, G, need = R["A"], R["G"], R["need"]
CAP = 262144
GRAPH = "d0973e97224a3136c168184c1715fe2e4e32acf664036a8a71728699fae6438d"


def reference(folder):
    root = R["load"](folder / "receipt.json", GRAPH)
    p = folder / "DIRECT/stdout"
    need(
        root["status"] == "PASS_TINY_GRAPH_BANK_INPUT"
        and R["sha"](p) == root["raw_sha256"]["DIRECT/stdout"],
        "qualified service trace",
    )
    events = []
    sets = {}
    for line in p.read_text().splitlines():
        s = line.split()
        if s[0] == "BANK_FENCE":
            gen = int(s[2])
            events.append(("IDS", gen, (gen - 1) % 2, *map(int, s[6].split(","))))
        elif s[0] == "SET" and s[5].startswith("moe_cache.") and s[5].endswith("_exps.weight"):
            sets[int(s[2])] = (s[5], int(s[7]))
        elif s[0] == "BANK_SOURCE":
            name, dest = sets.pop(int(s[2]))
            gen, layer, file, n = map(int, (s[3], s[5], s[7], s[10]))
            (il, role), _ = G["weight_slice"](file, n)
            need(il == layer, "wrong reference layer")
            events.append(
                ("SET", gen, layer, f"blk.{layer}.ffn_{role}_exps.weight", name, file, dest, n)
            )
    need(len(events) == 28 and not sets, "incomplete reference events")
    return events


def layout(events):
    cursor = drains = peak = 0
    spans = []
    for e in events:
        if e[0] == "IDS":
            cursor = 0
            continue
        file, n = e[5], e[7]
        head = file % 4096
        reservation = (head + n + 4095) // 4096 * 4096
        need(reservation <= CAP, "one SET exceeds native scratch")
        if cursor + reservation > CAP:
            cursor = 0
            drains += 1
        spans.append((cursor + head, drains))
        cursor += reservation
        peak = max(cursor, peak)
    need(drains > 0, "no exercised reuse")
    return spans, drains, peak


def audit(mode, raw, log, native, model, expected):
    header = [s for s in log.splitlines() if s.startswith("TESY_NATIVE_")]
    spans, drains, peak = layout(expected)
    need(
        header[0] == f"TESY_NATIVE_INPUT {mode} {CAP} 1"
        and header[-1] == f"TESY_NATIVE_END 4 24 1148928 {drains}"
        and len(header) == 30,
        "source selection or native teardown",
    )
    origs = {s[0]: (int(s[1]), int(s[2]), int(s[3])) for s in G["records"](raw, "ORIG")}
    vmas = A["maps"](native / "maps")
    device = A["mapped_device"](model)
    inode = model.stat().st_ino
    ranges = mode == "PREAD_RANDOM"
    rows, arena = [], None
    for record, e in zip(header[1:-1], expected, strict=True):
        s = record.split()
        if e[0] == "IDS":
            need(s[0] == "TESY_NATIVE_IDS" and tuple(map(int, s[1:])) == e[1:], "native routed IDs")
            continue
        need(s[0] == "TESY_NATIVE_SET" and len(s) == 11, "SET record")
        gen, layer = map(int, s[1:3])
        f, d, n, orig, actual, drain = map(int, s[5:])
        need((gen, layer, s[3], s[4], f, d, n) == e[1:], "original range, destination or slot")
        base, length, start = origs[s[3]]
        v = A["region"](vmas, orig, n)
        need(
            0 <= orig - base <= length - n
            and f == start + orig - base
            and v[2] == "r--s"
            and v[3] + orig - v[0] == f
            and v[5] == inode
            and v[6] == [str(model.resolve())]
            and tuple(int(x, 16) for x in v[4].split(":")) == device,
            "native model source",
        )
        head, expected_drains = spans[len(rows)]
        need(drain == expected_drains, "native pressure fence order")
        if ranges:
            v = A["region"](vmas, actual, n)
            if arena is None:
                arena = actual - head
            need(
                v[2] == "rw-p"
                and v[4:6] == ("00:00", 0)
                and not v[6]
                and arena > 0
                and arena % 4096 == 0
                and actual == arena + head,
                "scratch lifetime or address",
            )
        else:
            need(actual == orig, "direct source is not the GGUF")
        rows.append((3 if gen <= 2 else 4, s[4], d, n, orig, actual, f))
    index = 0
    pending = {}
    copies = defaultdict(list)
    all_h2d = []
    logical = []
    for line in raw.splitlines():
        s = line.split()
        if s and s[0] == "SET" and s[5].startswith("moe_cache.") and s[5].endswith("_exps.weight"):
            p, name, off, n, orig, actual, f = rows[index]
            index += 1
            ticket = int(s[2])
            need(
                ticket not in pending
                and s[3:6] == ["0", "async", name]
                and list(map(int, (s[1], s[7], s[8], s[9], s[10])))
                == [p, off, n, actual, -1 if ranges else f],
                "actual SET source",
            )
            pending[ticket] = (p, int(s[6]) + off, n, orig, actual, f)
            s[9:11] = map(str, (orig, f))
            line = " ".join(s)
        elif s and s[0] == "COPY" and s[4] in ("1", "4") and int(s[7]) > 0:
            ticket = int(s[2])
            dst, src, n, off, rc = map(int, s[5:10])
            all_h2d.append((src, n, ticket))
            if ticket in pending:
                p, dest, size, orig, actual, f = pending[ticket]
                rel = src - actual
                need(
                    0 <= rel < rel + n <= size
                    and s[3:5] == ["async", "1"]
                    and not rc
                    and int(s[1]) == p
                    and dst == dest + rel
                    and off == (-1 if ranges else f + rel),
                    "actual CUDART transfer",
                )
                copies[ticket].append((rel, n))
                s[6], s[8] = str(orig + rel), str(f + rel)
                line = " ".join(s)
        logical.append(line)
    need(index == len(rows) == 24 and set(pending) == set(copies), "missing physical SET/copy")
    for ticket, (_, _, n, _, _, _) in pending.items():
        G["coverage"](copies[ticket], n)
    need(sum(map(len, copies.values())) == 24, "unexpected number of physical copies")
    if ranges:
        need(
            all(t in pending for p, n, t in all_h2d if p < arena + CAP and arena < p + n),
            "unbound scratch H2D",
        )
    return "\n".join(logical) + "\n", dict(
        sets=24,
        physical_copies=24,
        id_fences=4,
        extra_drains=drains,
        scratch_capacity_B=CAP,
        scratch_peak_B=peak,
    )


def grade(label, folder, model, history, expected):
    raw = (folder / "stdout").read_text()
    log = (folder / "stderr").read_text()
    if label == "ORIGINAL":
        need("TESY_NATIVE_" not in log, "original library changed")
        view, proof = raw, None
    else:
        view, proof = audit(label, raw, log, folder / "native", model, expected)
    old = history / "BANK9"
    g = G["check_arm"]("BANK9", view, log, folder / "native")
    historical = R["R"]["SYS73"]["arm_grade"]("BANK9", old)
    need(
        g == historical and A["schedule"](view) == A["schedule"]((old / "stdout").read_text()),
        "changed bank execution",
    )
    resident = history / "RESIDENT"
    rg = R["R"]["SYS73"]["arm_grade"]("RESIDENT", resident)
    contrast = G["compare_arms"](resident / "native", rg, folder / "native", g)
    need(contrast["bitwise"] and contrast["routes_equal"], "resident logits or ranks")
    return dict(
        closure=proof,
        logits_sha256=g["logits_sha256"],
        quartets_sha256=g["ordered_top4_sha256"],
        consumer_ops=g["consumer_ops"],
        reference_bitwise=True,
    )
