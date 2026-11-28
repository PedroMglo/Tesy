"""Validate all numerical cuts and price only the measured final resident barriers."""

from collections import Counter

PAYLOAD = 13219200
ALIGNED = 13221888


def need(test, reason):
    if not test:
        raise ValueError(reason)


def cap_wait(row):
    calls, waves, _, _, _, _, _, normal_us, wave_us = row["counts"]
    return min(row["wall_ns"], (normal_us + wave_us + calls + waves) * 1000)


def verify(arms, work):
    ref = arms["S"]
    target = work["target"]
    schedule = {at: (q, d, n) for at, q, d, n in work["schedule"]}
    need(len(target) == 47 and target[-1] == 200002 and ref["role"] == "S", "serial target")
    for role, native in arms.items():
        observe = role in ("S", "B1")
        need(
            native["role"] == role
            and native["anchor"] == ref["anchor"]
            and [r["size"] for r in native["prefill"]] == [5, 148]
            and native["kv"] == ref["kv"],
            "anchor and KV cuts",
        )
        need(
            {int(k) for k in native["kv"]} == {1, *work["keep_counts"]}
            and all(
                v["public_max"] == len(work["t2"]) + int(k) - 2
                and 0 < v["bytes"] <= 96 << 20
                and len(bytes.fromhex(v["sha256"])) == 32
                for k, v in native["kv"].items()
            ),
            "complete KV fingerprints",
        )
        at = 1
        for i, row in enumerate(native["decode"]):
            offers, depth, kept = ([], 0, 1) if role == "S" else schedule[at]
            need(
                (row["at"], row["offers"], row["accepted"], row["keep"])
                == (at, offers, depth, kept),
                "causal schedule",
            )
            width = 1 + len(offers)
            need(
                len(row["ids"]) == len(row["hashes"]) == width
                and row["ids"][:kept] == target[at : at + kept]
                and all(len(bytes.fromhex(h)) == 32 for h in row["hashes"]),
                "native rows or target IDs",
            )
            need(
                row["hashes"][:kept]
                == [v["hashes"][0] for v in ref["decode"][at - 1 : at - 1 + kept]],
                "full consulted logits differ from serial",
            )
            if role != "S" and "B0a" in arms:
                other = arms["B0a"]["decode"][i]
                need(
                    all(
                        row[k] == other[k]
                        for k in ("ids", "offers", "hashes", "keep", "accepted", "at")
                    ),
                    "all branch logits, including rejected rows",
                )
            if observe:
                calls, waves, loads, size, hits, misses, preloads, wait, wave_wait = row["counts"]
                routes = row["routes"]
                need(
                    calls == 36
                    and waves == preloads == wave_wait == 0
                    and size == loads * PAYLOAD
                    and loads == misses
                    and len(routes) == 36
                    and all(
                        4 <= len(set(rr)) == len(rr) <= width * 4 and all(0 <= n < 128 for n in rr)
                        for rr in routes
                    )
                    and hits + misses == sum(map(len, routes)),
                    "demand and pack conservation",
                )
                for layer, union in enumerate(routes):
                    known = set().union(
                        *(r["routes"][layer] for r in ref["decode"][at - 1 : at - 1 + kept])
                    )
                    need(
                        known <= set(union) and (kept != width or known == set(union)),
                        "same target experts at confirmed input rows",
                    )
            else:
                need("counts" not in row and "routes" not in row, "observer OFF")
            at += kept
        need(at == len(target), "complete response")
        for row in native["prefill"] + native["decode"]:
            need(row["wall_ns"] > 0 and ("counts" in row) == observe, "wall or observer")
            if observe:
                ns = row["wall_ns"]
                c, w, loads, size, _, _, _, st, sw = row["counts"]
                need(
                    size == loads * PAYLOAD and 0 <= (st + sw) * 1000 <= ns + (c + w) * 1000,
                    "stall clock scope",
                )
    return True


def compact(native):
    result = {}
    for role, arm in native.items():
        rows = []
        for r in arm["decode"]:
            entry = {k: r[k] for k in ("at", "wall_ns", "accepted", "keep")}
            entry["width"] = len(r["ids"])
            if "counts" in r:
                entry["counts"] = r["counts"]
                entry["union_by_tier"] = [
                    sum(map(len, r["routes"][:25])),
                    sum(map(len, r["routes"][25:])),
                ]
            rows.append(entry)
        result[role] = dict(prefill=arm["prefill"], decode=rows)
    return result


def price(evidence, combined):
    obs = evidence["B1"]["decode"]
    groups = {
        "before": [
            i for i, r in enumerate(obs) if r["width"] == 3 and r["at"] + r["keep"] - 1 < 45
        ],
        "first": [i for i, r in enumerate(obs) if r["width"] == 3 and r["at"] <= 44],
        "all": [i for i, r in enumerate(obs) if r["width"] == 3],
    }
    need([len(i) for i in groups.values()] == [9, 10, 11], "first-content crossing")
    prices, totals, conservation = {}, {}, {}
    for role, arm in evidence.items():
        tally = Counter()
        for r in arm["decode"]:
            if "counts" in r:
                tally.update(
                    loads=r["counts"][2],
                    payload_B=r["counts"][3],
                    wait_us=r["counts"][7],
                    aligned_requested_B=r["counts"][2] * ALIGNED,
                    wall_ns=r["wall_ns"],
                )
        conservation[role] = dict(tally)
        if role == "S":
            continue
        costs = []
        for row, ref in zip(arm["decode"], obs, strict=True):
            need(
                all(row[k] == ref[k] for k in ("at", "width", "keep", "accepted")),
                "identical blocks",
            )
            costs.append(max(0, row["wall_ns"] - cap_wait(ref)))
        prices[role] = {k: sum(costs[i] for i in ix) for k, ix in groups.items()}
        totals[role] = {k: sum(arm["decode"][i]["wall_ns"] for i in ix) for k, ix in groups.items()}
    neutral = all(
        9 * totals[other][scope] <= 10 * totals["B1"][scope] <= 11 * totals[other][scope]
        for other in ("B0a", "B0b")
        for scope in ("before", "all")
    )
    limits = []
    for w in combined["result"]["N2"]["arms"]:
        if w["case"] != "nominal":
            continue
        first = w["first"]["free_target_ns"]
        decode = w["decode"]["free_target_ns"]
        for role in prices:
            q = prices[role]
            limits.append(
                dict(
                    W=w["W"],
                    prefill=w["prefill_source"],
                    replay=w["replay"],
                    role=role,
                    before_ns=first + q["before"],
                    first_ns=first + q["first"],
                    decode_ns=decode + q["all"],
                    first_budget_ns=10**10 - first,
                    decode_budget_ns=47 * 10**9 // 6 - decode,
                )
            )
    fail = [r["first_ns"] > 10**10 or r["decode_ns"] > 47 * 10**9 // 6 for r in limits]
    decision = (
        "INCONCLUSIVE"
        if not neutral or any(fail) != all(fail)
        else "NO_GO_BARRIER_ONLY"
        if all(fail)
        else "GO_FIXTURE_ONLY"
    )
    serial = evidence["S"]["decode"]
    comparison = []
    for i in groups["all"]:
        r = obs[i]
        ss = serial[r["at"] - 1 : r["at"] - 1 + r["keep"]]
        comparison.append(
            dict(
                at=r["at"],
                accepted=r["accepted"],
                serial_calls=len(ss),
                B3_loads=r["counts"][2],
                serial_loads=sum(x["counts"][2] for x in ss),
                B3_unique=sum(r["union_by_tier"]),
                potential_duplicate_ranks=432 - sum(r["union_by_tier"]),
                serial_ns=sum(x["wall_ns"] for x in ss),
                B3_ns=r["wall_ns"],
                B3_final_wait_us=r["counts"][7],
                serial_final_wait_us=sum(x["counts"][7] for x in ss),
            )
        )
    return dict(
        decision=decision,
        observer_neutral=neutral,
        wall_by_scope_ns=totals,
        after_credit_by_scope_ns=prices,
        arms=limits,
        conservation=conservation,
        blocks=comparison,
    )
