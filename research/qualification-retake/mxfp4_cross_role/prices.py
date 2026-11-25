"""Price compressed transport on the same prefills, per-job READ→SET chains and 47 tokens."""

import json
from collections import Counter
from pathlib import Path
from runpy import run_path

QUAL = Path(__file__).resolve().parents[1]
NAT = QUAL / "phase_fd/integrated/t1_manager_bank/policy_snapshot/natural"
TRANSPORT = NAT / "replay/decode_clock/transport"
review = run_path(TRANSPORT / "review_service.py")
need, pinned, sha = review["check"], review["pinned"], review["digest"]
PREFILL = "f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f"
DECODE = "aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a"
JOINT = "78a53e6d93fed1ad9a9236d74b60b234546d32041f5e572998240b243b82fb7e"
SERVICE = "27832256db8ae629ece5c8d95f1ce5e0d285c24cfddf3b7e110b92154ad4cbc1"
WINDOW = 13221888
PPM = 1000000
BUDGET = 10218355216
OUTSIDE = 2318241276
TOKENS = 47


def coverage(groups, keys, count):
    frequencies = Counter(
        (g["layer"], j["expert"]) for g in groups for j in g["jobs"] if j["source"] == "disk"
    )
    need(sum(frequencies.values()) == count, "disk coverage")

    def scope(population):
        repeats = sum(v for k, v in population.items() if k in keys)
        return dict(
            sample_distinct_keys=len(population.keys() & keys),
            sample_job_occurrences=repeats,
            all_distinct_keys=len(population),
            all_job_occurrences=sum(population.values()),
        )

    return {
        name: scope({k: v for k, v in frequencies.items() if match(k[0])})
        for name, match in (
            ("CPU", lambda layer: layer < 25),
            ("CUDA", lambda layer: layer >= 25),
            ("both", lambda _: True),
        )
    }


def pack_chains(root, order, groups, service, raw_digest):
    receipt = pinned(root / "receipt.json", raw_digest)
    need(
        receipt["status"] == "PASS_DECODE_NVME_SERVICE_PAIR"
        and receipt["order"] == order
        and receipt["plan_sha256"] == DECODE,
        "measured decode pair",
    )
    result = []
    supplied = Counter()
    file = root / "raw/P.jsonl"
    need(
        sha(file) == receipt["arms"]["P"]["groups_sha256"] == service["expected_data_sha256"],
        "pack journal",
    )
    with file.open() as stream:
        for group, line in zip(groups, stream, strict=True):
            row = json.loads(line)
            review["group"](group, row, "P")
            read_by_ordinal = {
                r["ordinal"]: r["read_spans_ns"][0][1] - r["read_spans_ns"][0][0]
                for r in row["jobs"]
            }
            chains = []
            for job in group["jobs"]:
                ordinal = job["ordinal"]
                need((ordinal in read_by_ordinal) == (job["source"] == "disk"), "job source")
                src = job["r0_same_site_set_ns"]
                supplied[(job["source"], src is not None)] += 1
                need(src is None or type(src) is int and src >= 0, "same-site SET")
                chains.append((read_by_ordinal.get(ordinal, 0), src or 0))
            if chains:
                result.append(chains)
    need(
        supplied == {("disk", True): 797, ("bank", True): 172, ("bank", False): 227},
        "SET homologues",
    )
    need(
        decode_scaled(result, 1, 1) == service["conditional"]["common_set_floor"]["total_ns"],
        "q=1 decode",
    )
    return result


def decode_scaled(chains, numerator, denominator):
    return OUTSIDE * denominator + sum(
        max(r * numerator + s * denominator for r, s in g) for g in chains
    )


def margins(chains, prefill, gap, numerator, denominator):
    decode = decode_scaled(chains, numerator, denominator)
    prefill_scaled = prefill * numerator
    joint = (BUDGET - gap) * denominator - prefill_scaled - decode
    six = TOKENS * 10**9 * denominator - 6 * decode
    return joint, six, decode


def cutoff(chains, prefill, gap):
    def eligible(q):
        joint, six, _ = margins(chains, prefill, gap, q, PPM)
        return min(joint, six) >= 0

    if not eligible(0):
        return None
    lo, hi = 0, PPM
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if eligible(mid):
            lo = mid
        else:
            hi = mid - 1
    need(eligible(lo) and (lo == PPM or not eligible(lo + 1)), "adjacent integer thresholds")
    return lo


def request_prices(
    prefill_plan, decode_plan, decode_rp_dir, decode_pr_dir, sample_keys, best_aligned_bytes
):
    keys = set(sample_keys)
    need(
        len(keys) == 64 and all(0 <= layer < 36 and 0 <= expert < 128 for layer, expert in keys),
        "64-expert sample",
    )
    need(
        type(best_aligned_bytes) is int
        and 0 < best_aligned_bytes <= WINDOW
        and best_aligned_bytes % 4096 == 0,
        "aligned transport floor",
    )
    pre = pinned(Path(prefill_plan), PREFILL)["groups"]
    dec = pinned(Path(decode_plan), DECODE)["groups"]
    joint = pinned(NAT / "prefill_frontier/transport/joint/receipt.json", JOINT)
    service = pinned(TRANSPORT / "service-evidence.json", SERVICE)
    sample_coverage = {"prefill": coverage(pre, keys, 1058), "decode": coverage(dec, keys, 797)}
    result = {}
    for i, (d, root) in enumerate((("RP", Path(decode_rp_dir)), ("PR", Path(decode_pr_dir)))):
        chains = pack_chains(
            root, d, dec, service["arms"][d]["P"], service["raw_receipt_sha256"][i]
        )
        for p in ("RP", "PR"):
            tag = p + "_" + d
            prefill = joint["arms"][p]["P"]["service_ns"]
            for gapcase, c in joint["conditional"].items():
                expected = c["pairs"][tag]
                gap = expected["gap_ns"]
                raw_joint, _, raw_decode = margins(chains, prefill, gap, 1, 1)
                need(
                    expected["observed_phase_budget_ns"] == BUDGET
                    and expected["margin_ns"] == raw_joint
                    and expected["decode_price_ns"] == raw_decode
                    and expected["prefill_read_service_ns"] == prefill,
                    "q=1 full paired price",
                )
                margin, six, price = margins(chains, prefill, gap, best_aligned_bytes, WINDOW)
                result.setdefault(gapcase, {})[tag] = dict(
                    q_ppm_max=cutoff(chains, prefill, gap),
                    gap_ns=gap,
                    q1_joint_margin_ns=raw_joint,
                    q1_decode_ns=raw_decode,
                    best_joint_margin_ns_floor=margin // WINDOW,
                    best_six_margin_ns_floor=six // (6 * WINDOW),
                    best_joint_margin_ns_numerator=margin,
                    best_decode_ns_numerator=price,
                    best_decode_rate_millitokens_per_s_floor=TOKENS * 10**12 * WINDOW // price,
                    meets_best_joint_and_six=min(margin, six) >= 0,
                )
    return dict(
        cases=result,
        coverage=sample_coverage,
        transport_record_bytes=WINDOW,
        best_q_numerator=best_aligned_bytes,
        best_q_denominator=WINDOW,
        decoded_output_tokens=TOKENS,
        observed_evaluations=46,
        unknown_set_chains_relaxed_to_zero=227,
        sources=dict(prefill_plan=PREFILL, decode_plan=DECODE, joint=JOINT, service=SERVICE),
    )
