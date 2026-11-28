"""Independently reconstruct read coverage, causal order and paired prices from native clocks."""

from statistics import median

MODES = ("FULL", "READY", "L32", "E32", "LALL", "EALL")
SLAB, WINDOW, PAGE = 4406400, 13221888, 4096
PAIR = {"E32": "L32", "EALL": "LALL"}


def need(value, message):
    if not value:
        raise ValueError(message)


def extents(mode):
    if mode in ("FULL", "READY"):
        return [[0, WINDOW]]
    n = 32 * 1530 if mode.endswith("32") else SLAB
    g = (n + PAGE - 1) // PAGE * PAGE
    a = 2 * SLAB // PAGE * PAGE
    b = (2 * SLAB + n + PAGE - 1) // PAGE * PAGE
    return [[0, g], [a, b], [g, a]] + ([[b, WINDOW]] if b < WINDOW else [])


def interval(i, start, end):
    return len(i) == 2 and start <= i[0] < i[1] <= end


def overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def trial(r, index):
    b, rep, mode = index
    need((r["block"], r["rep"], r["mode"]) == index, "paired order")
    split = mode in MODES[2:]
    small = mode.endswith("32")
    start, end = r["start"], r["end"]
    reads = r["reads"]
    cuts = extents(mode)
    need(
        r["extents"] == cuts
        and len(reads) == len(cuts)
        and sum(v - u for u, v in cuts) == WINDOW
        and all(interval(i, start, end) for i in reads)
        and all(a[1] <= z[0] for a, z in zip(reads[:-1], reads[1:], strict=True))
        and reads[-1][1] <= r["full"] < end
        and (r["copied"], r["sets"]) == (3 * SLAB, 5 if small else 3),
        "service coverage/clock",
    )
    w, act, suffix, down, red = (
        r[k] for k in ("resident", "activation", "suffix", "down", "reduction")
    )
    need(
        interval(w, start, end)
        and interval(red, start, end)
        and w[1] <= red[0]
        and r["full"] <= red[0]
        and (r["checked_weighted"], r["checked_ffn"], r["checked_stage_words"])
        == (11520, 2880, 23040 if split else 0),
        "numerical census or join",
    )
    if mode == "FULL":
        need(r["full"] <= w[0] and down == [0, 0], "FULL barrier")
    else:
        need(
            interval(down, max(w[1], r["full"]), red[0]),
            "down before resident or final weight publication",
        )
    if split:
        need(
            reads[1][1] <= r["partial"] <= reads[2][0]
            and interval(act, r["partial"] if mode.startswith("E") else r["full"], down[0])
            and (small or w[1] <= act[0]),
            "consumer admission",
        )
        if small:
            need(interval(suffix, max(w[1], r["full"], act[1]), down[0]), "suffix barrier")
        else:
            need(suffix == [0, 0], "extra suffix")
    else:
        need(r["partial"] == 0 and act == suffix == [0, 0], "unexpected split")
    return dict(
        elapsed=end - start,
        consumer_read_overlap=sum(overlap(act, span) for span in reads[2:]) if split else 0,
        consumer_service_overlap=overlap(act, [r["partial"], r["full"]]) if split else 0,
        consumer=act[1] - act[0],
        service=r["full"] - reads[0][0],
    )


def grade(data):
    need(
        data["order"] == [28, 24, 8, 16]
        and data["slots"] == [3, 14, 6, 35]
        and data["generations"] == [6, 6, 5, 4]
        and data["ggml_threads"] == 8
        and data["workers_joined"] == 4
        and 0 < data["mutant_unequal_ffn"] <= 2880
        and data["setup_bytes"] == 4 * 13258752,
        "authority, resources or mutant",
    )
    need(
        data["injected_tail"]
        == dict(extents=extents("E32")[:2], full_published=False, down_entered=False),
        "partial failure must prevent final publication",
    )
    design = [(-1, -1, mode) for mode in MODES] + [
        (b, rep, mode)
        for b in (0, 1)
        for rep in range(5)
        for mode in (MODES if b == 0 else tuple(reversed(MODES)))
    ]
    need(len(data["parity"]) == 6 and len(data["trials"]) == 60, "design size")
    results = {}
    for number, (r, idx) in enumerate(zip(data["parity"] + data["trials"], design, strict=True), 1):
        need(r["epoch"] == number, "stale service epoch")
        results[idx] = trial(r, idx)
    families = {}
    for early, late in PAIR.items():
        controls = ("FULL", "READY", late)
        blocks = []
        for b in (0, 1):
            pairs = {
                k: [results[b, i, k]["elapsed"] - results[b, i, early]["elapsed"] for i in range(5)]
                for k in controls
            }
            useful = [results[b, i, early]["consumer_read_overlap"] for i in range(5)]
            blocks.append(
                dict(
                    paired_savings_ns=pairs,
                    median_savings_ns={k: median(v) for k, v in pairs.items()},
                    consumer_read_overlap_ns=useful,
                    consumer_ns=[results[b, i, early]["consumer"] for i in range(5)],
                    median_elapsed_ns={
                        k: median(results[b, i, k]["elapsed"] for i in range(5))
                        for k in (*controls, early)
                    },
                )
            )
        good = all(
            min(b["median_savings_ns"].values()) > 0 and median(b["consumer_read_overlap_ns"]) > 0
            for b in blocks
        )
        loses = all(b["median_savings_ns"]["READY"] < 0 for b in blocks)
        ablated = all(b["median_savings_ns"][late] <= 0 for b in blocks)
        families[early] = dict(
            blocks=blocks,
            decision="GO_LOCAL" if good else "NO_GO_LOCAL" if loses or ablated else "INCONCLUSIVE",
        )
    return dict(
        families=families,
        exact_arms=66,
        timed_arms=60,
        paired_per_order=5,
        ordered_ffn_words=66 * 2880,
        weighted_words=66 * 11520,
        cold_stage_words=44 * 23040,
        pack_read_bytes=data["setup_bytes"]
        + 66 * WINDOW
        + sum(b - a for a, b in extents("E32")[:2]),
        timed_set_bytes=60 * 3 * SLAB,
        stage_archive_files=8,
        invalid_reduction_words=data["mutant_unequal_ffn"],
        slots_bytes=data["storage_bytes"],
    )
