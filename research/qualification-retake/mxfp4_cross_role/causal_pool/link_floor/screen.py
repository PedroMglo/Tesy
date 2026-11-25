"""Conditional serial-callback latency floor from the single NVMe PCIe link."""

import argparse
import json
import os
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
prev = run_path(HERE.parent / "screen.py")
lru, base, cost, need, pinned = [prev[k] for k in ("lru", "base", "cost", "need", "pinned")]
W = prev["W"]
S = 11259904
NS = 10**9
LINK = 8 * NS
PREVIOUS = "08c4f7fe5c8487202be6a24bb0b47e21a0f3bad155fd6dfc225f5b552ff389d3"
PLACED = "adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000"
PACK = "f17e9fbf6f6aed1ad60ca7da3431c5156a946d2e0bf119722afc1f934cbc6b11"


def floor(v):
    return v.numerator // v.denominator


def extra_time(pairs, bps):
    need(type(bps) is int and bps > 0, "positive integer B/s")
    return sum((max(0, F(volume * NS, bps) - known) for known, volume in pairs), start=F(0))


def required(pairs, available):
    if available < 0 or (available == 0 and any(k == 0 and u for k, u in pairs)):
        return None
    lo = 1
    hi = LINK
    while extra_time(pairs, hi) > available:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if extra_time(pairs, mid) <= available:
            hi = mid
        else:
            lo = mid + 1
    need(
        extra_time(pairs, lo) <= available and (lo == 1 or extra_time(pairs, lo - 1) > available),
        "minimum rate",
    )
    return lo


def available_volume(pairs, available):
    if available < 0:
        return None
    total = sum(u for _, u in pairs)
    # The link can spend the intersection credit in any subset of callbacks/jobs.
    overlap = sum(min(u, known * LINK / NS) for known, u in pairs)
    return min(total, floor(overlap + available * LINK / NS))


def placements(a):
    pl = pinned(a.placement, PLACED)
    need(
        pl["status"] == "PASS_NVME_C290_FULL_PACK_PLACEMENT"
        and pl["destination_device"] == "nvme0n1"
        and pl["destination_transport"] == "nvme"
        and pl["destination_sha256"] == pl["source_sha256"] == PACK
        and pl["size_bytes"] == pl["destination_reread_bytes"] == 61096329216,
        "placed pack",
    )
    stat = [pl["destination_stat"][k] for k in ("dev", "ino", "size", "mtime_ns", "ctime_ns")]
    service = pinned(cost["TRANSPORT"] / "service-evidence.json", cost["SERVICE"])
    for i, receipt in enumerate(service["raw_receipt_sha256"], 1):
        path = a.archive / f"part-66/tesy-decode-service-20261125-r0{i}/receipt.json"
        data = pinned(path, receipt)
        need(
            data["filesystem"] == "btrfs"
            and data["device"] == "nvme0n1"
            and data["sources"]["P"]
            == dict(layout_sha256=PACK, placement_sha256=PLACED, stat=stat),
            "measured source vs placement",
        )
    return dict(
        pack_sha256=PACK,
        placement_sha256=PLACED,
        device="nvme0n1",
        filesystem="btrfs",
        source_bytes=pl["size_bytes"],
        family_receipts=service["raw_receipt_sha256"],
    )


def assess(callbacks):
    groups = []
    certain = F(cost["OUTSIDE"])
    unknown_counts = Counter()
    for jobs in callbacks:
        need(len(jobs) <= 4, "at most four causal workers")
        known = max((F(read * S, W) + s for _, read, s in jobs if read is not None), default=F(0))
        certain += known
        n = sum(read is None for _, read, _ in jobs)
        if n:
            need(all(s == 0 for _, read, s in jobs if read is None), "ambiguous unknown CPU SET")
            groups.append((known, n * S))
            unknown_counts[n] += 1
    need(sum(n * c for n, c in unknown_counts.items()) == 254, "new CPU disk jobs")
    return groups, certain, unknown_counts


def calculate(a):
    old = pinned(a.combined, PREVIOUS)
    need(
        old["status"] == "REPRODUCED_COMBINED_PRICE" and old["best_size"] == S, "prior composition"
    )
    source = placements(a)
    pri, bank, ages, now, _ = lru["start_clock"](a.archive)
    groups, p, b, _, meas, _, joint, _, _ = base["inputs"](a.archive)
    need(p == pri and b == bank, "same seed")
    events, states = lru["simulate"](groups, pri, bank, ages, now, "U1262")
    witness = pinned(prev["LRU_DIR"] / "evidence/receipt.json", prev["LRU"])["arms"]["U1262"]
    need(
        states == witness["states"] and base["summarize"](groups, events) == witness["phase_work"],
        "paid causal replay",
    )
    plan = pinned(
        a.archive / "part-65/tesy-decode-transport-prepare-20261125-r01/plan.json", cost["DECODE"]
    )["groups"]
    split = len(groups) - len(plan)
    orders = {}
    common = {}
    for d, marks in meas.items():
        callbacks = prev["decode_callbacks"](groups[split:], events[split:], marks, plan)
        uncertain, known, count = assess(callbacks)
        certain, unc, n = prev["service"](callbacks, lambda _: S)
        need(
            n == 254
            and len(unc) == len(uncertain) == old["cpu_unknown_callbacks"]
            and certain == known * W,
            "zero-price precursor",
        )
        fixed_delta = extra_time(uncertain, LINK)
        all_bytes = sum(u for _, u in uncertain)
        only = sum(u for k, u in uncertain if k == 0)
        common[d] = dict(
            unknown_jobs=n,
            unknown_bytes=all_bytes,
            unknown_callbacks=len(uncertain),
            histogram=count,
            callbacks_without_known_chain=sum(k == 0 for k, _ in uncertain),
            bytes_without_known_chain=only,
            link_floor_ns_alone=floor(F(only * NS, LINK)),
            additional_link_floor_ns=floor(fixed_delta),
        )
        for pre, pop in joint["arms"].items():
            name = pre + "_" + d
            pf = F(pop["P"]["service_ns"] * 1048 * S, 1058 * W)
            before = cost["BUDGET"] - pf - known
            six = F(47 * NS, 6) - known
            prior = old["cases"]["uniform_best"][name]["zero"]
            need(
                floor(before) == prior["joint_margin_ns_floor"]
                and floor(six) == prior["six_margin_ns_floor"],
                "existing two budgets",
            )
            budget = min(before, six)
            maxbytes = available_volume(uncertain, budget)
            orders[name] = dict(
                before_joint_margin_ns_floor=floor(before),
                before_six_margin_ns_floor=floor(six),
                after_joint_margin_ns_floor=floor(before - fixed_delta),
                after_six_margin_ns_floor=floor(six - fixed_delta),
                new_decode_floor_ns=floor(known + fixed_delta),
                required_minimum_Bps=required(uncertain, budget),
                max_bytes_via_link=maxbytes,
                max_byte_fraction_ppm=None if maxbytes is None else maxbytes * 10**6 // all_bytes,
            )
    return dict(
        status="FORMAL_CONDITIONAL_NVME_LINK_FLOOR",
        program_sha256=prev["sha"](Path(__file__)),
        protocol_sha256=prev["sha"](HERE / "protocol.md"),
        link_observation_sha256=prev["sha"](HERE / "link.json"),
        placement=source,
        previous_sha256=PREVIOUS,
        host_transport_ceiling_Bps=LINK,
        encoded_bytes_per_job=S,
        orders=orders,
        decode=common,
        weight_bytes_read=0,
        model_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "combined", "placement", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = calculate(a)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=repr(exc))
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
