"""Audit every slot publication, service extent, barrier and paired price for the seven jobs."""

from collections import Counter
from statistics import median

W, GAP = 13221888, 36864
SEQUENCE = "FPSM"


def need(ok, msg):
    if not ok:
        raise ValueError(msg)


def validate(r, selection):
    mode = r["mode"]
    groups = [g["ids"] for g in r["accepted"]]
    fifo = [k[3] for k in selection["fifo"]]
    promoted = [47, 48, 3, 10, 82, 44, 98]
    order = fifo if mode == "F" else promoted
    expected = [[e] for e in order] if mode in "FP" else [[47, 48], *([e] for e in order[2:])]
    need(groups == expected and fifo == [47, 3, 10, 48, 82, 44, 98], "FIFO or promotion")
    pins = {k[3]: k[1:3] for k in selection["pins"]}
    pub = {int(e): v for e, v in r["published"].items()}
    need(
        set(pub) == set(order) and (r["checked_matrix_hashes"], r["remap_values"]) == (48, 128),
        "publication or numerical census",
    )
    start, resume, returned, drain = (r[k] for k in ("start", "resumed", "returned", "drained"))
    ends = r["worker_ends"]
    need(
        start < resume <= returned <= drain
        and len(ends) == 4
        and all(start <= end <= drain for end in ends),
        "barrier/drain",
    )
    previous = [start] * 4
    accepted = start
    expected_reads = []
    for g in r["accepted"]:
        i = g["worker"]
        need(0 <= i < 4 and max(previous[i], accepted) <= g["at"] < resume, "worker/dispatch clock")
        cursor = accepted = g["at"]
        merged = mode == "M" and len(g["ids"]) == 2
        for j, e in enumerate(g["ids"]):
            if not merged or j == 0:
                ids = g["ids"] if merged else [e]
                matches = [read for read in r["reads"] if read["ids"] == ids]
                need(len(matches) == 1, "read conservation")
                read = matches[0]
                need(
                    read["worker"] == i
                    and cursor <= read["begin"] < read["end"] <= resume
                    and read["bytes"] == len(ids) * W + (GAP if merged else 0),
                    "read/destination",
                )
                expected_reads.append(read)
                cursor = read["end"]
            published = pub[e]
            need(
                published["worker"] == i
                and [published["slot"], published["gen"]] == pins[e]
                and len(published["sets"]) == 3,
                "slot lineage",
            )
            for a, b in published["sets"]:
                need(cursor <= a < b <= resume, "SET before data")
                cursor = b
            need(cursor <= published["at"] <= min(resume, ends[i]), "early/stale publication")
            cursor = published["at"]
        previous[i] = cursor
    need(len(expected_reads) == len(r["reads"]), "extra read")
    total = sum(s["bytes"] for s in expected_reads)
    need(total == 7 * W + (GAP if mode == "M" else 0), "payload or padding")

    def end(e):
        return pub[e]["at"] - start

    return dict(
        barrier=returned - start,
        drain=drain - start,
        ready=max(map(end, order)),
        pair=max(end(47), end(48)),
        intervening=max(end(3), end(10)),
        e3=end(3),
        e10=end(10),
        e82=end(82),
        read_bytes=total,
        last=max(order, key=end),
    )


def grade(rows, selection):
    layout = [(-1, -1, mode) for mode in SEQUENCE] + [
        (b, i, mode)
        for b in (0, 1)
        for i in range(5)
        for mode in (SEQUENCE if b == 0 else SEQUENCE[::-1])
    ]
    need(len(rows) == len(layout) == 44, "arm count")
    times = {}
    for r, idx in zip(rows, layout, strict=True):
        need((r["block"], r["rep"], r["mode"]) == idx, "blocked comparisons")
        times[idx] = validate(r, selection)
    blocks = []

    def deltas(b, control, subject, clock):
        return [times[b, i, control][clock] - times[b, i, subject][clock] for i in range(5)]

    for b in (0, 1):
        outcomes = {}
        for ctl, subject in (("F", "M"), ("P", "M"), ("S", "M"), ("F", "P")):
            d = {
                key: deltas(b, ctl, subject, key)
                for key in ("barrier", "drain", "pair", "intervening", "e3", "e10", "e82", "ready")
            }
            outcomes[f"{ctl}-{subject}"] = dict(
                pairs_ns=d, medians_ns={k: median(v) for k, v in d.items()}
            )
        blocks.append(
            dict(
                contrasts=outcomes,
                median_barrier_ns={
                    m: median(times[b, i, m]["barrier"] for i in range(5)) for m in SEQUENCE
                },
                last_counts={
                    m: dict(Counter(times[b, i, m]["last"] for i in range(5))) for m in SEQUENCE
                },
            )
        )
    costs = [b["contrasts"] for b in blocks]
    merge_good = all(
        all(b[k]["medians_ns"]["barrier"] > 0 for k in ("F-M", "P-M", "S-M"))
        and b["F-M"]["medians_ns"]["drain"] > 0
        for b in costs
    )
    fm = [b["F-M"]["medians_ns"]["barrier"] for b in costs]
    improvement = [b["F-P"]["medians_ns"]["barrier"] for b in costs]
    return dict(
        merged="GO_LOCAL" if merge_good else "NO_GO_LOCAL" if max(fm) < 0 else "INCONCLUSIVE",
        promotion="GO_LOCAL"
        if min(improvement) > 0
        else "NO_GO_LOCAL"
        if max(improvement) < 0
        else "INCONCLUSIVE",
        blocks=blocks,
        meets_isolated_price=min(fm) >= 6950087,
        requested_bytes=sum(t["read_bytes"] for t in times.values()),
        sha_checks=48 * len(rows),
        physical_ids_checked=128 * len(rows),
        published_generations=7 * len(rows),
        set_bytes=len(rows) * 7 * 3 * 4406400,
    )
