"""Grade all identities, last-reader events and mirrored pairs of the CPU0 fixture."""

from statistics import median

ROLES = ("COPY40", "COPY1252", "DRAIN", "LAST")
CASES = ("five", "many")
WINDOW = 13221888
FFN = {
    "five": "bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24",
    "many": "b518f0dbd870d437f3e3b6275c89102daae3d65fe173bac58177f14677e88d52",
}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def validate_native(native, case, phase):
    need(native["case"] == case and native["phase"] == phase, "native case")
    records, expert, positions, first = (9, 45, 153, 32) if case == "five" else (70, 30, 32, 0)
    need(
        native["pack_reads"] == records
        and native["matrix_hashes"] == 3 * records
        and native["witness_expert"] == expert
        and native["router"]["positions"] == positions
        and native["router"]["first"] == first,
        "true target coverage",
    )
    for row in native["rows"]:
        role = row["role"]
        need(
            row["hit_sets"] == (3 if role.startswith("COPY") else 0)
            and row["weight_frames"] == (40 if role == "COPY40" else 1252)
            and row["wave_calls"] == row["mask_calls"] == 8
            and 0
            < row["before_down_ns"]
            <= row["down_done_ns"]
            <= row["graph_ns"]
            <= row["drained_ns"]
            and (row["ffn"] == FFN[case]) == (role != "EARLY")
            and (row["different_F32"] == 0) == (role != "EARLY")
            and len(row["workers"]) == 4,
            "FFN, geometry or epoch",
        )
        held = row["workers"][0]
        for j, w in enumerate(row["workers"]):
            need(
                0 < w["claim_ns"] <= w["writable_ns"] <= w["published_ns"] <= row["drained_ns"],
                "worker interval",
            )
            if j or role.startswith("COPY"):
                need(not w["blocked"], "independent writer blocked")
            if phase == "exact" and j:
                need(w["published_ns"] <= row["before_down_ns"], "peer blocked by delayed consumer")
        if role.startswith("COPY"):
            need(row["release_ns"] == 0, "copy retained source")
        else:
            if phase == "exact":
                need(
                    held["blocked"] and held["claim_ns"] <= row["before_down_ns"],
                    "uncontended exact arm",
                )
            need(held["writable_ns"] >= row["release_ns"] > 0, "write before release")
            if role == "LAST":
                need(row["down_done_ns"] <= row["release_ns"] <= row["graph_ns"], "last read")
            elif role == "DRAIN":
                need(row["release_ns"] >= row["graph_ns"], "early drain")
            elif role == "EARLY":
                need(
                    row["before_down_ns"]
                    <= row["release_ns"]
                    <= held["published_ns"]
                    <= row["down_done_ns"],
                    "fault was not delivered before the last consumer",
                )
    need(len({row["other_sets"] for row in native["rows"]}) == 1, "other deliveries changed")


def exact_result(native, case):
    validate_native(native, case, "exact")
    rows = native["rows"]
    need([r["role"] for r in rows] == [*ROLES, "EARLY"], "exact order")
    reference = rows[0]["cuts"]
    need(
        len(reference) == 84 and all(r["cuts"] == reference for r in rows[1:4]),
        "full intermediate parity",
    )
    fault = rows[-1]["cuts"]
    need(fault.keys() == reference.keys(), "mutant coverage")
    different = [name for name in sorted(fault) if fault[name] != reference[name]]
    need(
        all("0/" + k not in different for k in ("up", "up_bias", "gate", "gate_bias", "activation"))
        and all(str(w) + "/mask" not in different for w in range(8))
        and all(k in different for k in ("0/down", "0/down_bias", "0/sum", "rank_sum3")),
        "mutant did not isolate the last weight reader",
    )
    return dict(
        control_and_safe_arms=4,
        finite_intermediates_per_arm=len(reference),
        ffn_F32=32 * 2880,
        mutant_different_F32=rows[-1]["different_F32"],
        changed_cuts=different,
    )


def prices(native, case):
    validate_native(native, case, "price")
    rows = native["rows"]
    expected = [(0, 0, r) for r in ROLES]
    for p in range(1, 8):
        for d, order in enumerate((ROLES, ROLES[::-1])):
            expected.extend((p, d, r) for r in order)
    need(
        [(r["block"], r["direction"], r["role"]) for r in rows] == expected
        and not any("cuts" in row for row in rows),
        "uncounted schedule",
    )
    indexed = {(r["block"], r["direction"], r["role"]): r for r in rows}
    directions = []
    for d in (0, 1):
        groups = {role: [indexed[p, d, role] for p in range(1, 8)] for role in ROLES}
        arms = {}
        for role, g in groups.items():
            arms[role] = dict(
                drained_ns=median(r["drained_ns"] for r in g),
                graph_ns=median(r["graph_ns"] for r in g),
                wait_ns=median(
                    r["workers"][0]["writable_ns"] - r["workers"][0]["claim_ns"] for r in g
                ),
                delayed_claims=sum(r["workers"][0]["blocked"] for r in g),
                workspace_B=sorted({r["workspace_B"] for r in g}),
            )
        pairs = {}
        for baseline, candidate in (
            ("COPY40", "LAST"),
            ("COPY1252", "LAST"),
            ("DRAIN", "LAST"),
            ("COPY40", "COPY1252"),
        ):
            delta = [
                x["drained_ns"] - v["drained_ns"]
                for x, v in zip(groups[baseline], groups[candidate], strict=True)
            ]
            pairs[baseline + "-" + candidate] = dict(
                ns=delta, median_ns=median(delta), positive=sum(v > 0 for v in delta)
            )
        directions.append(dict(direction=d, arms=arms, comparisons=pairs))
    return directions


def grade(exact, price):
    out = {}
    for case in CASES:
        need(exact[case]["router"] == price[case]["router"], "routing changed across gates")
        out[case] = dict(exact=exact_result(exact[case], case), prices=prices(price[case], case))

    def contrast(base):
        return [
            p["comparisons"][base + "-LAST"]["median_ns"] for c in out.values() for p in c["prices"]
        ]

    narrow, wide = contrast("COPY40"), contrast("COPY1252")
    if min(*narrow, *wide) > 0:
        verdict = "GO_COMPONENT_RAW_LAYER"
    elif max(narrow) < 0:
        verdict = "NO_GO_SINGLE_HIT_VS_NARROW"
    else:
        verdict = "INCONCLUSIVE_LAYER_COST"
    return dict(
        status="MEASURED_ROUTED_CPU0",
        numerical="GO_AFTER_DOWN",
        cost=verdict,
        cases=out,
        full_model_forwards=0,
        HTTP_requests=0,
        gpu_compute=False,
        M3="PARTIAL",
        M4="NOT_MET",
    )
