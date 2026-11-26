"""Reopen the timed C110 arms against the measured selective and direct R03 schedules."""

import hashlib
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PARENT = run_path(str(HERE.parent / "grade.py"))
FR, A, need = (PARENT[k] for k in ("FR", "A", "need"))
FAMILY = "051b5f102cf26c96470e7cf7369205ae3ac9443daa72f14300a3b8d6c2d943d3"
ORDER = {"D1": "DIRECT", "P1": "PREAD_RANDOM", "P2": "PREAD_RANDOM", "D2": "DIRECT"}
PHASES = ("prefill", "teacher", "cleanup")
PAGES = (63387346208 + 4095) // 4096


def schedule(raw):
    sets, sites, tickets = [], [], {}
    phase_bytes = {3: 0, 4: 0}
    for line in raw.splitlines():
        s = line.split()
        if not s:
            continue
        if s[0] == "SET" and s[5].startswith("moe_cache.") and s[5].endswith("_exps.weight"):
            phase, ticket, dest, size, file = map(int, (s[1], s[2], s[7], s[8], s[10]))
            need(ticket not in tickets and s[4] == "async", "unknown or duplicate SET")
            tickets[ticket] = phase, s[5], dest, size, file
        elif s[0] == "BANK_FENCE":
            phase, gen = map(int, s[1:3])
            need(gen == len(sites) + 1, "fence order")
            sites.append(" ".join(("IDS", str(phase), str(gen), *s[6].split(","))))
        elif s[0] == "BANK_SOURCE":
            p, name, dest, size, offset = tickets.pop(int(s[2]))
            phase, gen, layer, file, n = map(int, (s[1], s[3], s[5], s[7], s[10]))
            need((p, size, offset, len(sites)) == (phase, n, file, gen), "SET/source mismatch")
            sets.append(f"SET {phase} {gen} {layer} {name} {file} {dest} {n}")
            phase_bytes[p] += n
    need(
        not tickets
        and len(sets) == 2925
        and len(sites) == 72
        and phase_bytes == {3: 14752627200, 4: 1692057600},
        "incomplete reference schedule",
    )
    return "\n".join(sets + sites) + "\n"


def reference(folder):
    family = A["receipt"](folder / "receipt.json", FAMILY)
    need(family["status"] == "PASS_C110_BANK_INPUT_NUMERIC", "numerical prerequisite")
    refs = []
    for label in ("DIRECT_OFF", "PREAD_OFF"):
        p = folder / label
        arm = A["receipt"](p / "receipt.json", family["arms"][label]["receipt_sha256"])
        need(
            arm["status"] == "PASS_C110_BANK_INPUT_ARM" and FR["inventory"](p) == arm["raw_sha256"],
            "qualified raw",
        )
        need(
            arm["physical"]["bank_sets"] == arm["physical"]["physical_copies"] == 2925
            and arm["physical"]["id_fences"] == 72
            and arm["physical"]["fills_at_cleanup"] == 6,
            "qualified graph",
        )
        refs.append(
            (
                schedule((p / "raw/stdout").read_text()),
                {str(pos): A["sha"](p / "native" / f"pos{pos}.f32") for pos in (15, 16)},
            )
        )
    need(refs[0] == refs[1], "qualified schedules or rows differ")
    return refs[0]


def grade(label, folder, gold):
    service, row_sha = gold
    native = folder / "native"
    need(
        (native / "service.tsv").read_text() == service,
        "changed route, generation, file range or physical slot",
    )
    rows = FR["available_rows"](folder)
    for pos, top in (("15", 3659), ("16", 3992)):
        r = rows[pos]
        need(
            r["sha256"] == row_sha[pos]
            and r["bytes"] == 804352
            and r["finite"]
            and r["max_ties"] == 1
            and r["top5"][0] == top,
            "C110 row mismatch",
        )
    lines = (folder / "raw/stdout").read_text().splitlines()
    tags = {"CB_EVAL", "COLD_GGUF", "BANK_MODE", "BANK_END", "ROW", "KV", "CONTEXT", "STATUS"}
    expected = [
        "CB_EVAL OFF",
        "BANK_MODE " + ORDER[label],
        f"COLD_GGUF {PAGES} 0 {PAGES}",
        "CONTEXT 8192 1 256 32 0 0",
        "KV 15 16",
        "ROW 15 201088 3659 1",
        "KV 16 17",
        "ROW 16 201088 3992 1",
        "BANK_END 72 6",
        "STATUS COMPLETED_IK_GPU_BANK_CUTS",
    ]
    need(
        [s for s in lines if s.partition(" ")[0] in tags] == expected,
        "cold, observer, KV, rows or cleanup",
    )
    need(
        not any(
            s.startswith(
                (
                    "COPY ",
                    "BANK_SOURCE ",
                    "BANK_GET ",
                    "BANK_FENCE ",
                    "SET 3 ",
                    "SET 4 ",
                    "NODE ",
                    "SUBMIT ",
                )
            )
            for s in lines
        ),
        "heavy observer enabled",
    )
    clocks = [s.split()[1:] for s in lines if s.startswith("GRAPH_NS ")]
    need(len(clocks) == 1 and len(clocks[0]) == 3, "native clocks")
    times = dict(zip(PHASES, map(int, clocks[0]), strict=True))
    need(min(times.values()) > 0, "empty native interval")
    return dict(
        status="PASS_C110_PRICE_ARM",
        native_ns=times,
        total_ns=sum(times.values()),
        service_sha256=hashlib.sha256(service.encode()).hexdigest(),
        logits_sha256=row_sha,
        cold_pages=PAGES,
        resident_before_load=0,
        ordered_quartets=597,
        sites=72,
        bank_sets=2925,
    )


def compare(arms):
    pairs = []
    for d, p in (("D1", "P1"), ("D2", "P2")):
        pair = {k: arms[d]["native_ns"][k] - arms[p]["native_ns"][k] for k in PHASES}
        pairs.append(pair | {"total": sum(pair.values())})
    times = [v["total"] for v in pairs]
    if min(times) > 0:
        choice = "GO_NATURAL_WORKLOAD"
    elif max(times) <= 0:
        choice = "NO_GO_COLD_C110"
    else:
        choice = "INCONCLUSIVE"
    return dict(decision=choice, direct_minus_pread_ns=pairs)
