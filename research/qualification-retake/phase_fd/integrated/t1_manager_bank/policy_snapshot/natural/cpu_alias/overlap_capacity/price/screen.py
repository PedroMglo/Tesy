"""Price the fixed eighteen reads eliminated by the causal CPU alias extension."""

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
cap = run_path(HERE.parent / "score.py")
NAT = cap["NAT"]
q = run_path(NAT / "prefill_frontier/transport/joint/review.py")
d = run_path(NAT / "replay/decode_clock/transport/review_service.py")
need = cap["need"]
CAPACITY = "40606cf47c0442fdf046272a0c85a1599f59997e5feab86fc15754c46ac7bb70"
JOINT = "78a53e6d93fed1ad9a9236d74b60b234546d32041f5e572998240b243b82fb7e"
SERVICE = "27832256db8ae629ece5c8d95f1ce5e0d285c24cfddf3b7e110b92154ad4cbc1"


def encoded(x):
    return (json.dumps(x, sort_keys=True, indent=2) + "\n").encode()


def key(g, j):
    return tuple(g[x] for x in ("call", "tile", "layer", "wave")) + tuple(
        j[x] for x in ("ordinal", "expert", "slot", "generation")
    )


def selected(a, prefill, decode):
    expected = q["pinned"](HERE.parent / "receipt.json", CAPACITY)
    need(hashlib.sha256(encoded(cap["score"](a))).hexdigest() == CAPACITY, "capacity replay")
    rows, _ = cap["replay"]["fd"].read_journal(a.family / "ON/raw/events.pfj")
    cutoff = json.loads((a.family / "ON/before-t2.json").read_bytes())["records"]
    slots, fifo, victims = cap["replay"]["audit"]["state_before"](rows[:cutoff])
    need(not fifo, "T1 drain")
    k = cap["K"]
    bank_list = list(dict.fromkeys(reversed(victims)))[:k][::-1]
    bank = set(bank_list)
    primary = {(i // 40, s[0]) for i, s in enumerate(slots)}
    store, _ = cap["before_post"](rows[:cutoff], bank_list, primary)
    extra = set(store.order) - bank
    need(
        hashlib.sha256(json.dumps(sorted(extra)).encode()).hexdigest()
        == expected["causal"]["entry_extra_sha256"],
        "T1 extra membership",
    )
    state = [(s[0], s[1]) for s in slots]
    result = set()
    counts = Counter()
    for phase, groups in (("prefill", prefill), ("decode", decode)):
        for g in groups:
            layer = g["layer"]
            for j in g["jobs"]:
                s = j["slot"] + 40 * layer
                old, gen = state[s]
                incoming = (layer, j["expert"])
                need(
                    gen + 1 == j["generation"]
                    and old == j.get("victim", old)
                    and (j["source"] == "bank") == (incoming in bank),
                    "saved job binding",
                )
                if incoming in store.order and j["source"] == "disk":
                    tag = key(g, j)
                    need(tag not in result and incoming in extra, "double count or future extra")
                    result.add(tag)
                    counts[phase] += 1
                primary.remove((layer, old))
                primary.add(incoming)
                state[s] = (incoming[1], gen + 1)
                store.trim(primary, k)
    need(
        counts == {"prefill": 14, "decode": 4}
        and len({(v[2], v[5]) for v in result}) == 16
        and len(store.order) - k == expected["causal"]["last_extra_count"],
        "causal population",
    )
    return result


def fifo(prices):
    available = [0] * 4
    for t in prices:
        need(type(t) is int and t > 0, "nonpositive READ")
        worker = min(range(4), key=available.__getitem__)
        available[worker] += t
    return max(available)


def price_prefill(root, digest, order, groups, selected_sites, joint):
    sense = q["pinned"](root / "receipt.json", digest)
    arm = sense["arms"]["P"]
    need(
        sense["order"] == order
        and sense["plan_sha256"] == cap["PREFILL"]
        and arm["verified_components"] == 3174
        and sense["status"] == "PASS_PREFILL_FULL_QUEUE_PAIR",
        "prefill pass/plan",
    )
    raw = root / "raw/P.jsonl"
    gold = root / "raw/P-integrity.jsonl"
    need(
        q["sha"](raw) == arm["raw_sha256"] and q["sha"](gold) == arm["verification_sha256"],
        "prefill raw identity",
    )
    out = []
    with raw.open() as stream, gold.open() as verify:
        for tokens, line, proof, summary in zip(
            (5, 148), stream, verify, arm["calls"], strict=True
        ):
            row = json.loads(line)
            expected = [
                (g, j)
                for g in groups
                if g["call_tokens"] == tokens
                for j in g["jobs"]
                if j["source"] == "disk"
            ]
            need(
                row["call_tokens"] == tokens
                and row["elapsed_ns"] == summary["dispatch_to_drain_ns"],
                "call release",
            )
            hist = q["inspect_jobs"](row["jobs"], expected, "P", summary)
            q["inspect_integrity"](json.loads(proof), expected)
            prices = []
            remaining = []
            removed = []
            kept_spans = []
            for rawjob, (g, j) in zip(row["jobs"], expected, strict=True):
                ((lo, hi),) = rawjob["read_spans_ns"]
                elapsed = hi - lo
                prices.append(elapsed)
                if key(g, j) in selected_sites:
                    removed.append(elapsed)
                else:
                    remaining.append(elapsed)
                    kept_spans.append((lo, hi))
            base_fifo = fifo(prices)
            new_fifo = fifo(remaining)
            union = summary["read_union_ns"]
            unique = union - d["union"](kept_spans)
            need(
                len(removed) == (1 if tokens == 5 else 13)
                and sum(prices) == summary["read_worker_ns"]
                and 0 <= unique <= sum(removed)
                and 0 <= base_fifo - new_fifo <= sum(removed),
                "four-server/union envelope",
            )
            out.append(
                dict(
                    call_tokens=tokens,
                    original_jobs=len(expected),
                    saved_jobs=len(removed),
                    dq4_ns=hist[4],
                    measured_dispatch_to_drain_ns=row["elapsed_ns"],
                    measured_read_worker_ns=sum(prices),
                    removed_read_worker_ns=sum(removed),
                    measured_read_union_ns=union,
                    removed_exclusive_union_ns=unique,
                    model_baseline_ns=base_fifo,
                    model_candidate_ns=new_fifo,
                    model_delta_ns=base_fifo - new_fifo,
                )
            )
    need(
        sum(x["measured_dispatch_to_drain_ns"] for x in out)
        == joint["arms"][order]["P"]["service_ns"],
        "published prefill wall",
    )
    return out


def remove_read(chains):
    return max((r + s for r, s, _ in chains), default=0) - max(
        (s + (0 if hit else r) for r, s, hit in chains), default=0
    )


def price_decode(root, digest, order, groups, selected_sites, report):
    meta = d["pinned"](root / "receipt.json", digest)
    arm = meta["arms"]["P"]
    path = root / "raw/P.jsonl"
    need(
        meta["order"] == order
        and meta["status"] == "PASS_DECODE_NVME_SERVICE_PAIR"
        and meta["plan_sha256"] == cap["DECODE"]
        and d["digest"](path) == arm["groups_sha256"] == report["expected_data_sha256"],
        "decode raw and plan",
    )
    rows = []
    old = 0
    with path.open() as f:
        for g, line in zip(groups, f, strict=True):
            row = json.loads(line)
            proven, _ = d["group"](g, row, "P")
            measured = {
                r["ordinal"]: r["read_spans_ns"][0][1] - r["read_spans_ns"][0][0]
                for r in row["jobs"]
            }
            chains = [
                (
                    measured.get(j["ordinal"], 0),
                    j["r0_same_site_set_ns"] or 0,
                    key(g, j) in selected_sites,
                )
                for j in g["jobs"]
            ]
            old += proven["common_set_floor"]
            affected = [(r, s) for r, s, hit in chains if hit]
            if affected:
                rows.append(
                    dict(
                        call=g["call"],
                        step=g["step"],
                        layer=g["layer"],
                        saved_jobs=len(affected),
                        removed_worker_ns=sum(r for r, _ in affected),
                        retained_same_site_set_ns=sum(s for _, s in affected),
                        prior_critical_ns=proven["common_set_floor"],
                        critical_delta_ns=remove_read(chains),
                    )
                )
    fixed = d["OUTSIDE"]
    need(
        fixed + old == report["conditional"]["common_set_floor"]["total_ns"]
        and sum(x["saved_jobs"] for x in rows) == 4,
        "published decode wall",
    )
    delta = sum(x["critical_delta_ns"] for x in rows)
    return dict(
        sites=rows,
        baseline_ns=fixed + old,
        candidate_ns=fixed + old - delta,
        constant_outside_ns=fixed,
        delta_ns=delta,
    )


def calculate(a):
    pre = q["pinned"](a.prefill, cap["PREFILL"])["groups"]
    dec = q["pinned"](a.decode, cap["DECODE"])["groups"]
    joint = q["pinned"](NAT / "prefill_frontier/transport/joint/receipt.json", JOINT)
    service = q["pinned"](NAT / "replay/decode_clock/transport/service-evidence.json", SERVICE)
    sites = selected(a, pre, dec)
    pprice = {}
    dprice = {}
    for i, order in enumerate(("RP", "PR")):
        pprice[order] = price_prefill(
            getattr(a, "pre_" + order.lower()),
            joint["raw_receipt_sha256"][i],
            order,
            pre,
            sites,
            joint,
        )
        dprice[order] = price_decode(
            getattr(a, "dec_" + order.lower()),
            service["raw_receipt_sha256"][i],
            order,
            dec,
            sites,
            service["arms"][order]["P"],
        )
    pairs = {}
    for p in pprice:
        for order in dprice:
            tag = p + "_" + order
            base = joint["conditional"]["all_gaps_free"]["pairs"][tag]
            need(
                base["prefill_read_service_ns"]
                == sum(j["measured_dispatch_to_drain_ns"] for j in pprice[p])
                and base["decode_price_ns"] == dprice[order]["baseline_ns"]
                and base["margin_ns"] < 0,
                "same request",
            )
            sim = sum(j["model_delta_ns"] for j in pprice[p]) + dprice[order]["delta_ns"]
            ceiling = (
                sum(j["removed_read_worker_ns"] for j in pprice[p]) + dprice[order]["delta_ns"]
            )
            pairs[tag] = dict(
                initial_deficit_ns=-base["margin_ns"],
                breakeven_model_ns=sim,
                breakeven_fixed_service_ceiling_ns=ceiling,
                remaining_deficit_even_at_ceiling_ns=-base["margin_ns"] - ceiling,
            )
    return dict(
        status="TRACE_DERIVED_MARGINAL_SERVICE_PRICES",
        protocol_sha256=q["sha"](HERE / "protocol.md"),
        program_sha256=q["sha"](Path(__file__)),
        capacity_sha256=CAPACITY,
        joint_sha256=JOINT,
        decode_authority_sha256=SERVICE,
        saved_sites_sha256=hashlib.sha256(encoded(sorted(sites))).hexdigest(),
        prefill=pprice,
        decode=dprice,
        pairs=pairs,
        weight_bytes_read=0,
        model_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for keyname in (
        "family",
        "prefill",
        "decode",
        "pre-rp",
        "pre-pr",
        "dec-rp",
        "dec-pr",
        "new-output-dir",
    ):
        p.add_argument("--" + keyname, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = calculate(a)
        (a.new_output_dir / "receipt.json").write_bytes(encoded(result))
    except Exception as exc:
        (a.new_output_dir / "failure.json").write_bytes(
            encoded(dict(status="FAIL_PRESERVED", reason=repr(exc)))
        )
        raise


if __name__ == "__main__":
    main()
