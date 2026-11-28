"""Verify CPU renewal, real traffic, clocks and paired results in the native C291 fixture."""

import statistics
from itertools import product

ROLES = ("DISK", "COPY", "ID")
WINDOW = 13221888
SPAN = 2880 * 4
SHARED_B = 16553807883


def need(ok, message):
    if not ok:
        raise ValueError(message)


def order():
    for block in range(8):
        for direction in range(2):
            for role in ROLES if direction == 0 else ROLES[::-1]:
                yield block, direction, role


def verify(d, role, exact):
    if role == "EIO":
        need(
            d["role"] == role
            and d["failed_closed"]
            and d["reads"] == 8
            and d["sets"] == 21
            and d["published_before_fault"] == 4
            and d["quarantined_expert"] == 47,
            "short-read quarantine",
        )
        return
    bank = role != "DISK"
    need(
        d["role"] == role
        and d["phase"] == ("exact" if exact else "price")
        and d["workers"] == 4
        and 0 < d["reading_workers"] <= 4
        and d["arena_B"] == SHARED_B
        and d["reservations"] == 16
        and d["bank_entries"] == (4 if bank else 0)
        and d["loans"] == d["releases"] == 22
        and d["staged_hits"] == 0
        and d["copies"] == (8 if role == "COPY" else 0)
        and len(d["rows"]) == 4
        and 0 < d["prepared_ns"] <= d["setup_and_phases_ns"] <= d["process_through_teardown_ns"],
        "topology, capacity, physical loans or counters",
    )
    for i, r in enumerate(d["rows"]):
        hit = bank and i >= 2
        contested = i != 0 and exact
        need(
            r["phase"] == i
            and r["reads"] == (0 if hit else 4)
            and r["hits"] == (4 if hit else 0)
            and r["captures"] == (4 if bank and i else 0)
            and r["sets"] == (0 if hit and role != "COPY" else 12),
            "unpaid source or copy",
        )
        need(
            r["peers_before"] == contested
            and r["protected_after_first"] == contested
            and r["stale_rejected"] == contested
            and r["first_before"] == (contested and bank),
            "old reader lost or peer dispatch blocked",
        )
        need(
            len(set(r["frames"])) == 4
            and all(0 <= f < 1252 for f in r["frames"])
            and (r["computed"] == r["frames"]) == (role != "WRONG" or i != 3),
            "physical rank view",
        )
        need(
            0
            <= r["accepted_ns"]
            <= r["released_ns"]
            <= r["ready_ns"]
            <= r["result_ns"]
            <= r["drain_ns"]
            and 0 <= r["old_compute_ns"] <= r["released_ns"]
            and (r["old_compute_ns"] > 0) == bool(i)
            and len(r["publication_ns"]) == 4
            and all(0 < t <= r["ready_ns"] for t in r["publication_ns"]),
            "publication, release, arithmetic or drain",
        )
        if exact:
            need(
                len(r["hashes"]["sha256"]) == len(r["hashes"]["first_rank"]) == 3, "numerical cuts"
            )
        else:
            need(r["hashes"] is None, "unexpected hashing in timing")
    need(
        d["reads"] == sum(r["reads"] for r in d["rows"])
        and d["sets"] == sum(r["sets"] for r in d["rows"]),
        "whole trial traffic",
    )


def verify_exact(exact, differences, independent):
    need(
        set(exact) == set(ROLES) | {"WRONG", "EIO"} and set(differences) == {"COPY", "ID", "WRONG"},
        "exact population",
    )
    for role, r in exact.items():
        verify(r, role, True)
        if role == "EIO":
            continue
        for i, phase in enumerate(r["rows"]):
            if i % 2 and not (role == "WRONG" and i == 3):
                need(phase["hashes"]["sha256"] == independent, "independent A projection")
            if role != "DISK":
                for k, h in enumerate(phase["hashes"]["sha256"]):
                    delta = differences[role][3 * i + k]
                    equal = h == exact["DISK"]["rows"][i]["hashes"]["sha256"][k]
                    need(
                        0 <= delta <= SPAN and equal == (delta == 0) == (role != "WRONG" or i != 3),
                        "wrong rank fault or raw F32 comparison",
                    )


def median(ns):
    return int(statistics.median(ns))


def elapsed(r):
    def total(rows, name):
        return sum(x[name] for x in rows)

    formation, promotions = r["rows"][:2], r["rows"][2:]
    return dict(
        formation_result_ns=total(formation, "result_ns"),
        promotions_result_ns=total(promotions, "result_ns"),
        promotions_ready_ns=total(promotions, "ready_ns"),
        old_compute_ns=total(promotions, "old_compute_ns"),
        formation_and_hits_ns=total(r["rows"], "result_ns"),
        through_teardown_ns=r["process_through_teardown_ns"],
        setup_ns=r["prepared_ns"],
        cleanup_after_phases_ns=r["process_through_teardown_ns"] - r["setup_and_phases_ns"],
        promotion_publish_ns=sum(max(x["publication_ns"]) for x in promotions),
    )


def grade(native):
    verify_exact(native["exact"], native["differences"], native["independent_A"])
    rows = native["price"]
    expected = list(order())
    need([(r["block"], r["direction"], r["role"]) for r in rows] == expected, "paired arm order")
    by = {}
    for r in rows:
        verify(r, r["role"], False)
        by[r["block"], r["direction"], r["role"]] = elapsed(r)
    directions = []
    for direction in range(2):
        measures = {
            role: {
                k: median([by[b, direction, role][k] for b in range(1, 8)])
                for k in by[1, direction, role]
            }
            for role in ROLES
        }
        contrasts = {}
        for role, metric in product(("DISK", "COPY"), by[1, direction, "ID"]):
            ns = [
                by[b, direction, role][metric] - by[b, direction, "ID"][metric] for b in range(1, 8)
            ]
            contrasts.setdefault(role, {})[metric] = dict(
                ns=ns, positive=sum(t > 0 for t in ns), median_ns=median(ns)
            )
        directions.append(
            dict(direction=direction, medians=measures, paired_control_minus_ID=contrasts)
        )
    signs = [
        d["paired_control_minus_ID"][r]["promotions_result_ns"]["median_ns"]
        for d in directions
        for r in ("DISK", "COPY")
    ]
    status = (
        "GO_MEASURED_RENEWAL_PRICE"
        if min(signs) > 0
        else ("NO_GO_LOCAL_PRICE" if max(signs) < 0 else "INCONCLUSIVE_RENEWAL_PRICE")
    )
    return dict(
        status=status,
        correctness="GO_NATIVE_RENEWAL_LEASE",
        evidence="MEASURED_COMPONENT_LAPTOP",
        directions=directions,
        measured_trials=42,
        warmup_trials=6,
        F32_per_complete_exact_arm=12 * SPAN,
        wrong_F32_per_projection=native["differences"]["WRONG"],
        pack_requested_B=WINDOW * sum(x["reads"] for x in [*native["exact"].values(), *rows]),
        integrated_product_gain_ns=None,
        model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
        M3="PARTIAL",
        M4="NOT_MET",
    )
