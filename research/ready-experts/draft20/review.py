"""Reconstruct every accepted ID and price each target block on its own W clock."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parsed(raw, ids):
    lines = iter(raw.splitlines())

    def fields(tag, n):
        row = next(lines).split()
        need(len(row) == n + 1 and row[0] == tag, "missing or unordered " + tag)
        return row[1:]

    need(fields("vocabulary", 1) == ["201088"], "vocabulary mismatch")
    cases = {}
    for name in ("nominal", "code"):
        target = ids[name]
        need(fields("case", 1) == [name], "case order")
        mode, ready = fields("prefill", 2)
        need(mode == "serial" and int(ready) > 0, "serial prompt")
        reference, serial_ns = [], []
        for pos in range(len(target) - 1):
            i, q, ns = map(int, fields("serial", 3))
            need(i == pos and 0 <= q < 201088 and ns > 0, "draft reference")
            reference.append(q)
            serial_ns.append(ns)
        mode, prefix = fields("prefill", 2)
        need(mode == "blocks" and int(prefix) > 0, "block prompt")
        blocks, tails = [], []
        at = 1
        while at + 2 < len(target):
            i, q1, q2, depth, t1, t2, undo, align = map(int, fields("block", 8))
            need(i == at and q1 == reference[at - 1] and 0 <= q2 < 201088, "first proposal")
            expected = 0
            if q1 == target[at]:
                need(q2 == reference[at], "second proposal on accepted prefix")
                expected = 1 + int(q2 == target[at + 1])
            need(depth == expected, "individual target decisions")
            blocks.append([at, depth, t1, t2, undo, align])
            at += 1 + depth
        while at < len(target):
            i, ns = map(int, fields("tail", 2))
            need(i == at and ns > 0, "serial tail")
            tails.append(ns)
            at += 1
        need(fields("end", 1) == [name], "case not drained")
        cases[name] = dict(
            serial_ns=serial_ns,
            serial_matches=[q == v for q, v in zip(reference, target[1:], strict=True)],
            serial_prefill_ns=int(ready),
            block_prefill_ns=int(prefix),
            blocks=blocks,
            tail_ns=tails,
        )
    need(next(lines) == "done" and next(lines, None) is None, "incomplete native output")
    return cases


def replay(case):
    matches = case["serial_matches"]
    need(len(case["serial_ns"]) == len(matches) and min(case["serial_ns"]) > 0, "serial coverage")
    at = 1
    rows = []
    for i, depth, t1, t2, undo, align in case["blocks"]:
        need(i == at and at + 2 <= len(matches), "block boundary")
        expected = int(matches[at - 1]) * (1 + int(matches[at]))
        need(depth == expected and min(t1, t2) > 0 and min(undo, align) >= 0, "block evidence")
        need((undo > 0) == (depth == 0) and (align > 0) == (depth == 2), "KV conservation")
        pos = at - 1
        at += 1 + depth
        rows.append((pos, at - 1, t1 + t2, undo + align))
    remaining = len(matches) + 1 - at
    need(
        0 <= remaining <= 2
        and len(case["tail_ns"]) == remaining
        and all(ns > 0 for ns in case["tail_ns"]),
        "tail conservation",
    )
    return rows


def price(rows, clocks, cut, wall, limit):
    """Return an allocation in ns per block; an atomic B3 pays in full at a crossing."""
    ticks = clocks["ticks_ns"]
    covered = [r for r in rows if r[0] < cut]
    need(covered and 0 < cut < len(ticks), "empty cut")
    span = ticks[cut] - ticks[0]
    tail = ticks[cut] - ticks[min(cut, rows[-1][1])]
    # Draft KV alignment after the last admitted block is unnecessary at this cut.
    proposal = sum(r[2] for r in covered)
    maintenance = sum(r[3] for r in covered[:-1])
    allowance = limit - wall + span - tail
    n = len(covered)
    meet = allowance - proposal - maintenance
    return dict(
        blocks=n,
        cut_index=cut,
        straddles=covered[-1][1] > cut,
        covered_native_ns=span - tail,
        serial_tail_ns=tail,
        signed_exterior_ns=wall - span,
        proposal_ns=proposal,
        prior_alignment_and_undo_ns=maintenance,
        last_alignment_and_undo_granted_ns=covered[-1][3],
        free_draft_target_ns_per_block=allowance // n,
        paid_proposals_target_ns_per_block=(allowance - proposal) // n,
        paid_draft_target_ns_per_block=meet // n,
        zero_target_paid_draft_wall_ns=limit - meet,
        # The expression is invariant to limit, for the existing W prefill and outside work.
    )


def score(evidence):
    results = {}
    for name in ("nominal", "code"):
        case = evidence["draft"][name]
        rows = replay(case)
        n = len(case["serial_ns"]) + 1
        need(n == (47 if name == "nominal" else 256), "unexpected work")
        arms = []
        for w in evidence["clocks"][name]:
            ticks = w["ticks_ns"]
            need(
                len(ticks) == n
                and ticks[0] == 0
                and all(a < b for a, b in zip(ticks[:-1], ticks[1:], strict=True)),
                "producer clock",
            )
            cut, first, decode = w["cut"], w["first_final_ns"], w["decode_ns"]
            need(ticks[cut - 1] <= w["feed_ns"] <= ticks[cut], "SSE feed not ordered")
            need(abs(decode - ticks[-1]) <= 100_000, "native/server decode clock residual")
            first_limit = 10**10 if name == "nominal" else first
            decode_limit = n * 10**9 // 6 if name == "nominal" else decode
            f = price(rows, w, cut, first, first_limit)
            z = price(rows, w, n - 1, decode, decode_limit)
            arms.append(
                dict(
                    W=w["arm"],
                    first_final=f,
                    decode=z,
                    max_prefill_at_free_target_ns=w["prefill_ns"]
                    + first_limit
                    - f["zero_target_paid_draft_wall_ns"],
                    sample_after_previous_feed_ns=ticks[cut] - w["feed_ns"],
                    preserve_first_target_ns_per_block=price(rows, w, cut, first, first)[
                        "paid_draft_target_ns_per_block"
                    ],
                    preserve_decode_target_ns_per_block=price(rows, w, n - 1, decode, decode)[
                        "paid_draft_target_ns_per_block"
                    ],
                )
            )
        depths = [b[1] for b in case["blocks"]]
        results[name] = dict(
            samples=n,
            first_final_sample=evidence["clocks"][name][0]["cut"] + 1,
            teacher_matches=sum(case["serial_matches"]),
            proposals=2 * len(depths),
            accepted=sum(depths),
            block_depths=[depths.count(i) for i in range(3)],
            blocks=len(depths),
            serial_tail=len(case["tail_ns"]),
            confirmed_prefix_rows=n - 1,
            arms=arms,
        )
    cannot = all(
        a["first_final"]["paid_proposals_target_ns_per_block"] < 0
        for a in results["nominal"]["arms"]
    )
    return dict(
        cases=results,
        decision=(
            "NO_GO_SERIAL_CPU_DRAFT_AT_FIXED_NOMINAL_EXTERIOR"
            if cannot
            else "INCONCLUSIVE_JOINT_COST_REQUIRED"
        ),
        integrated_product="NOT_RUN",
        m3="PARTIAL",
        m4="NOT_MET",
    )


def acquire(inputs, physical):
    manifest = read(inputs / "receipt.json")
    receipt = read(physical / "receipt.json")
    provenance = read(physical / "provenance.json")
    need(
        sha(physical / "provenance.json") == receipt["provenance_sha256"]
        and sha(inputs / "receipt.json") == provenance["input_sha256"]
        and receipt["status"] == "MEASURED_20B_STANDALONE"
        and receipt["forwards_120b"] == 0
        and receipt["execution"]["live_providers"]
        and receipt["c118_s"] >= 60,
        "physical identity",
    )
    for label, key in (("draft", "execution"), ("hash", "hash")):
        for suffix in ("stdout", "stderr", "samples"):
            ext = suffix + (".jsonl" if suffix == "samples" else "")
            need(
                sha(physical / f"{label}.{ext}") == receipt[key][suffix + "_sha256"],
                "changed raw capture",
            )
    need(all(sha(inputs / k) == h for k, h in manifest["files"].items()), "changed trajectory")
    true_ids = {
        name: [x[0] for x in struct.iter_unpack("<i", (inputs / f"{name}-target.i32").read_bytes())]
        for name in ("nominal", "code")
    }
    return dict(
        physical_sha256=sha(physical / "receipt.json"),
        provenance_sha256=receipt["provenance_sha256"],
        clocks=manifest["cases"],
        inputs_sha256=provenance["input_sha256"],
        draft=parsed((physical / "draft.stdout").read_text(), true_ids),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", type=Path)
    p.add_argument("--inputs", type=Path)
    p.add_argument("--physical", type=Path)
    p.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    if a.check:
        saved = read(a.check)
        if a.inputs or a.physical:
            need(
                a.inputs and a.physical and acquire(a.inputs, a.physical) == saved["evidence"],
                "archive disagrees",
            )
        final = score(saved["evidence"])
        need(final == saved["result"], "published prices disagree")
    else:
        need(
            a.inputs and a.physical and a.new_output_dir,
            "supply both originals and a new directory",
        )
        a.new_output_dir.mkdir(mode=0o700)
        try:
            evidence = acquire(a.inputs, a.physical)
            final = score(evidence)
            with (a.new_output_dir / "receipt.json").open("x") as f:
                json.dump(
                    dict(evidence=evidence, result=final),
                    f,
                    separators=(",", ":"),
                    sort_keys=True,
                    allow_nan=False,
                )
                f.write("\n")
        except Exception as exc:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc))) + "\n"
            )
            raise
    print(final["decision"])
