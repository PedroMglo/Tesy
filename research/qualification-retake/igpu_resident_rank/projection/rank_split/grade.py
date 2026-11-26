"""Verify the split parity gates and report all paired local contrasts."""

import hashlib
from statistics import median

NAMES = ("Full", "Serial", "Free")
THRESHOLDS = {
    "six_low": 812000,
    "six_high": 954000,
    "first_final_low": 7557000,
    "first_final_high": 7741000,
}


def need(ok, label):
    if not ok:
        raise ValueError(label)


LEAVES = {
    "x": "f4b7b1fc1595244c263e292a8cd2d6c1d3c939e00b56e151c5c5d48fc403092e",
    "logical": "0132e8af7db0cae65ffcd07b97da7e7445368d95ffb0528723b92ac4ddb16d1e",
    "physical": "91b5009ad8fffc726414c61e3dc1fd5f3dd1e4ac48a05ecd1bebe61517052ec0",
    "mix": "2144b1ce76f2161a0ae725f6341c7811c33c5c4ae16366620736103704feb18d",
}


def grade(payload, ranks, ffn):
    need(
        payload["order"] == [28, 24, 8, 16]
        and payload["physical"] == [3, 14, 6, 35]
        and payload["generations"] == [6, 6, 5, 4]
        and payload["threads"] == 8,
        "original geometry",
    )
    word_hash = [
        hashlib.sha256(ranks[i : i + 11520]).hexdigest() for i in range(0, len(ranks), 11520)
    ]
    need(
        len(word_hash) == 4
        and hashlib.sha256(ranks).hexdigest() == payload["weighted_sha256"]
        and hashlib.sha256(ffn).hexdigest() == payload["ffn_sha256"],
        "anchors",
    )
    if payload["status"].startswith("FAIL_"):
        n = len(payload.get("timings", []))
        need(n == 0 or payload["status"] == "FAIL_TIMED_EXACTNESS", "clocks before admission")
        return dict(status=payload["status"], timed_graphs=n, evidence=payload)
    hashes = word_hash + [payload["ffn_sha256"]]
    exact = True
    for mode in NAMES:
        work = payload["parity"][mode]
        rows = [*work["weighted"], work["ffn"]]
        need(len(rows) == 5, "4 ranked rows and FFN")
        for r, h in zip(rows, hashes, strict=True):
            need(
                type(r["unequal"]) is int
                and 0 <= r["unequal"] <= 2880
                and type(r["nonfinite"]) is int
                and 0 <= r["nonfinite"] <= 2880
                and (r["unequal"] == 0) == (r["sha256"] == h),
                "parity proof",
            )
            exact &= r["unequal"] == r["nonfinite"] == 0
    if not exact:
        need(
            payload["status"] == "NO_GO_CROSS_SHAPE_EXACTNESS" and "timings" not in payload,
            "timing before parity",
        )
        return {"status": payload["status"], "timed_graphs": 0, "parity": payload["parity"]}
    fault = payload["negative"]
    need(
        fault["weighted"][0]["sha256"] == word_hash[1]
        and fault["weighted"][0]["unequal"] > 0
        and all(
            r["unequal"] == r["nonfinite"] == 0 and r["sha256"] == h
            for r, h in zip(fault["weighted"][1:], word_hash[1:], strict=True)
        )
        and fault["ffn"]["unequal"] > 0
        and fault["ffn"]["nonfinite"] == 0
        and fault["ffn"]["sha256"] != hashes[-1],
        "fault sensitivity",
    )
    need(payload["timed_input_checks"] == [14, 14, 14], "repetition leaf checks")
    for mode in NAMES:
        expected = LEAVES | ({"free_e28": word_hash[0]} if mode == "Free" else {})
        for phase in ("initial", "after_parity", "after_warmup"):
            proof = payload["inputs"][mode][phase]
            need(
                proof == dict(exact=True, observed=expected, expected=expected),
                "stable input " + mode + " " + phase,
            )
        need(payload["warmup"][mode] == payload["parity"][mode], "warmup gold")
    wrong = LEAVES | {"free_e28": word_hash[1]}
    for field in ("negative_inputs_before", "negative_inputs_after"):
        need(payload[field] == dict(exact=True, observed=wrong, expected=wrong), "negative inputs")
    timing = payload["timings"]
    need(
        payload["status"] == "PASS_RESIDENT_RANK_SPLIT_EXACT_TIMINGS" and len(timing) == 42,
        "timing status/count",
    )
    last = 0
    contrasts = {m: [] for m in NAMES[1:]}
    for block in range(2):
        for repeat in range(7):
            times = {}
            for j, mode in enumerate(NAMES if not block else reversed(NAMES)):
                r = timing[block * 21 + repeat * 3 + j]
                need(
                    (r["block"], r["rep"], r["mode"]) == (block, repeat, mode)
                    and type(r["start_ns"]) is int
                    and type(r["end_ns"]) is int
                    and last <= r["start_ns"] < r["end_ns"],
                    "arm order/clock",
                )
                last = r["end_ns"]
                times[mode] = last - r["start_ns"]
            for m in contrasts:
                contrasts[m].append(times["Full"] - times[m])

    def summarize(ds):
        medians = [median(ds[:7]), median(ds[7:])]
        return dict(
            paired_ns=ds,
            block_medians_ns=medians,
            median_ns=median(ds),
            min_ns=min(ds),
            max_ns=max(ds),
            thresholds={
                k: (
                    "BOTH_BLOCK_MEDIANS_REACH"
                    if min(medians) >= v
                    else "NEITHER_BLOCK_MEDIAN_REACHES"
                    if max(medians) < v
                    else "BLOCK_DEPENDENT"
                )
                for k, v in THRESHOLDS.items()
            },
        )

    return dict(
        status=payload["status"],
        timed_graphs=42,
        pairs=14,
        thresholds_ns=THRESHOLDS,
        contrasts={m: summarize(ds) for m, ds in contrasts.items()},
        parity=payload["parity"],
        negative=fault,
    )
