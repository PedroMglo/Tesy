"""Independent integer/binary oracle for the four native C291 CPU transition cases."""

import json
from collections import Counter
from hashlib import sha256

W = 13_219_200
ARMS = ("reference", "disk", "bank", "broken")
RECORDS = {0: 1, 6: 1, 1: 2, 7: 2, 43: 2, 2: 3, 40: 3, 3: 4, 41: 4, 44: 4, 42: 5}
TARGET = [43, 44, 42, 3, 41, 5, 6, 7, *range(8, 40)]
RESTORE_SLOTS = (0, 1, 2, 4, 6, 7)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_wave(w, pool, next_pair, index):
    count = 4 if index == 0 else 2
    a, b, c, d = pool
    bits = [1, 1, 1, 1, 1, 1, 0, 0]
    mask = bits if index == 0 else [1 - x for x in bits]
    ids = pool * 2 if index == 0 else [a, b, c, d, c, d, a, b]
    require(w["pool"] == pool and w["demand_slots"] == pool[:count], "pool or demand")
    require(w["ids"] == ids and w["mask"] == mask, "rank order, parking or mask")
    require(w["keep"] == [int(i in pool or i in next_pair) for i in range(40)], "keep")


def case(arm, row, gold):
    require(
        row["arm"] == arm and arm in ARMS and row["status"] == "PASS_C291_TILE_TRANSITION_CPU",
        "case",
    )
    require(
        row["workers"] == 4 and row["destructor_returned"] is True and row["preloads"] == 3,
        "workers/preloads",
    )
    reference = arm == "reference"
    bslots = (4, 2, 0, 1) if reference else (2, 4, 6, 7)
    pools = ([0, 1, 2, 3], [6, 4, 0, 1], [3, 5, *bslots[:2]], [*bslots[2:], 3, 5])
    for n, (wave, pool, keep_extra) in enumerate(
        zip(row["waves"], pools, ([6, 4], [], bslots[2:], []), strict=True)
    ):
        check_wave(wave, pool, keep_extra, n % 2)

    digests = {i: gold["records"][RECORDS.get(i, 0)]["role_sha256"] for i in range(45)}
    require(all(len(d) == 3 for d in digests.values()), "gold width")
    require(
        row["old_reader"]
        == {
            "6": digests[43 if arm == "broken" else 6],
            "4": digests[42 if arm == "broken" else 40],
        },
        "last consumer bytes",
    )
    require(
        row["capture"]
        == (
            None
            if reference
            else {"expert": 6, "slot": 6, "generation": 1, "role_sha256": digests[6]}
        ),
        "capture",
    )
    require(
        row["capture_bytes"] == (0 if reference else W)
        and row["scratch_bytes"] == (0 if reference else 4 * W),
        "scratch/capture bytes",
    )
    jobs = {(j["phase"], j["expert"]): j for j in row["jobs"]}
    require(len(jobs) == len(row["jobs"]), "duplicate claimed job")
    experts, generations = [-1] * 40, [0] * 40
    seen = set()
    usage = Counter()

    def apply(phase, expert, slot, source):
        key = (phase, expert)
        require(key in jobs and key not in seen, "missing or repeated generation")
        job = jobs[key]
        seen.add(key)
        generations[slot] += 1
        experts[slot] = expert
        require(
            (job["slot"], job["generation"], job["source"]) == (slot, generations[slot], source),
            "job identity/source",
        )
        require(
            (job["reads"], job["sets"], job["publications"]) == (int(source == "disk"), 3, 1),
            "job reads/SET/publication",
        )
        usage[phase + "_" + source] += 1

    for e in range(40):
        apply("warm", e, e, "disk")
    apply("A", 40, 4, "disk")
    for e, s in enumerate(bslots, 41):
        apply("B", e, s, "disk")

    def descriptors():
        return [
            {"expert": e, "slot": s, "generation": generations[s]} for s, e in enumerate(experts)
        ]

    require(row["before_restore"] == descriptors(), "pre-restoration table")
    held = {
        (h["expert"], h["slot"], h["generation"], h["state"], int(h["claimed"]))
        for h in row["held_jobs"]
    }
    require(
        len(row["held_jobs"]) == row["held_distinct_workers"] == 4
        and held == {(e, s, generations[s], 1, 1) for e, s in enumerate(bslots, 41)},
        "four in-flight claims",
    )
    for s in () if reference else RESTORE_SLOTS:
        expert = TARGET[s]
        source = (
            "scratch" if s in (0, 1, 2, 4) else ("bank" if s == 6 and arm != "disk" else "disk")
        )
        apply("restore", expert, s, source)
    require(
        set(jobs) == seen and experts == TARGET and row["decode_ids"] == [6, 7, 2, 4],
        "work or first-decode identity",
    )
    terminal = [dict(d, role_sha256=digests[d["expert"]]) for d in descriptors()]
    require(row["terminal"] == terminal, "terminal generations or payload")
    return {
        "claims": len(seen),
        "disk_reads": sum(j["reads"] for j in row["jobs"]),
        "sets": 3 * len(seen),
        "publications": len(seen),
        "terminal_payload_sha256": sha256(
            json.dumps([x["role_sha256"] for x in terminal], separators=(",", ":")).encode()
        ).hexdigest(),
        "sources": dict(sorted(usage.items())),
    }


def family(rows, gold):
    require(set(rows) == set(ARMS), "family coverage")
    result = {arm: case(arm, rows[arm], gold) for arm in ARMS}
    require(
        len({r["terminal_payload_sha256"] for r in result.values()}) == 1,
        "primary payload mismatch",
    )
    require(
        rows["bank"]["terminal"] == rows["broken"]["terminal"]
        and rows["bank"]["old_reader"] != rows["broken"]["old_reader"],
        "false-positive control",
    )
    return result
