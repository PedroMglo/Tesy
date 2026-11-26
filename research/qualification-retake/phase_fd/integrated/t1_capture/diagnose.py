"""Diagnose the frozen T1 capture failure; the original gate remains FAIL.

Before inspecting differences, compare the full ordered host/FIFO projections,
each kind separately, and per-site ordered and unordered events. Compare actual
rank order per row, demand identities and physical bindings, reservations with
victims, and worker publications. Report the earliest differing field and site;
publish no routing IDs. Preserve the exact private first discrepancy separately.
"""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("failed_t1_audit", HERE / "audit.py")
audit = importlib.util.module_from_spec(sp)
sp.loader.exec_module(audit)
fd = audit.fd
check = audit.check
HIST = audit.PRIOR
CURRENT = "40d2ea8049ccee9213ffc3f317482d67ebbed85a887a933043a3f4e7bd132033"
FAIL = "fc368b04cc5ea6258c05594ab52306c336446f40ab06ea2ec5fe287eabfeef5d"
BEFORE = "ad0d2e5445663f9f798a57c535b64abc631f1a898cc5cade0403c3fd734f94b4"
AUDIT = "8421320989e437594d4026d350269b07c3bb3c0c540a3d79f011a06534480089"
FIELD = {
    1: ("width", "position_first", "position_last"),
    3: ("width", "position_first", "position_last"),
    4: ("status", "b"),
    9: ("routed_rows", "top_k"),
    23: ("a", "b"),
    27: ("packed_ranks", "row"),
    10: ("expert", "slot", "generation", "a"),
    11: ("expert", "slot", "generation", "old_expert"),
    12: ("expert", "slot", "generation", "reason"),
}
SKEY = ("kind", "call", "tile", "layer", "wave")
WORKER_KEYS = ("expert", "slot", "generation")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def validate(path, digest):
    check(sha(path) == digest, "seal: " + path.name)
    return json.loads(path.read_bytes())


def save(path, data):
    with path.open("x") as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def first_change(current, prior):
    for n, (left, right) in enumerate(zip(current, prior, strict=False)):
        if left != right:
            index = n
            break
    else:
        if len(current) == len(prior):
            return None
        index = min(len(current), len(prior))
        left = current[index] if index < len(current) else None
        right = prior[index] if index < len(prior) else None
    active = left if left is not None else right
    names = (*SKEY, *FIELD.get(active[0], WORKER_KEYS))
    fields = (
        ["length"]
        if left is None or right is None
        else [f for f, a, b in zip(names, left, right, strict=False) if a != b]
    )
    return {"index": index, "fields": fields, "current": left, "prior": right}


def visible(change):
    if change is None:
        return None
    ans = {"index": change["index"], "fields": change["fields"]}
    for side in ("current", "prior"):
        row = change[side]
        ans[side] = dict(zip(SKEY, row[:5], strict=True)) if row is not None else None
        if row is not None:
            names = FIELD.get(row[0], WORKER_KEYS)
            for name, val in zip(names[: len(row) - 5], row[5:], strict=True):
                if name not in ("expert", "old_expert", "packed_ranks"):
                    ans[side][name] = val
    return ans


def per_site(left, right):
    def grouped(v):
        sites = defaultdict(list)
        for row in v:
            sites[row[:5]].append(tuple(row[5:]))
        return sites

    a, b = grouped(left), grouped(right)
    sites = a.keys() | b.keys()
    return dict(
        sites=len(sites),
        differing_sequences=sum(a[s] != b[s] for s in sites),
        differing_multisets=sum(Counter(a[s]) != Counter(b[s]) for s in sites),
    )


def comparison(left, right):
    return dict(
        current_count=len(left),
        prior_count=len(right),
        ordered_equal=left == right,
        multiset_equal=Counter(left) == Counter(right),
        sites=per_site(left, right),
        current_sha256=audit.digest(left),
        prior_sha256=audit.digest(right),
        first=visible(first_change(left, right)),
    )


def rank_comparison(current, prior, geometry):
    def expand(table):
        out = {}
        for _, call, tile, layer, wave, packed, row in table:
            k = call, tile, layer, wave, row
            check(k not in out, "duplicate ranked row")
            out[k] = tuple((packed >> (8 * i)) & 255 for i in range(4))
        return out

    a, b = expand(current), expand(prior)
    keys = sorted(a.keys() | b.keys())
    different = [k for k in keys if a.get(k) != b.get(k)]
    first = None
    if different:
        c, t, layer, wave, r = different[0]
        pos = geometry[c, t][1] if layer == 35 else geometry[c, t][0] + r
        key = different[0]
        first = dict(
            call=c,
            tile=t,
            layer=layer,
            wave=wave,
            row=r,
            absolute_position=pos,
            changed_rank_indices=[
                i for i in range(4) if a.get(key, (None,) * 4)[i] != b.get(key, (None,) * 4)[i]
            ],
        )
    return dict(
        rows=len(keys),
        changed_rows=len(different),
        shared_rows=len(a.keys() & b.keys()),
        first=first,
        changed_rank_sets=sum(set(a.get(k, ())) != set(b.get(k, ())) for k in different),
    )


def run(capture, prior):
    check(sha(HERE / "audit.py") == AUDIT and sha(audit.SOURCE) == audit.PIN, "auditor identity")
    failure = validate(capture / "receipt.json", FAIL)
    check(
        failure["status"] == "FAIL_PRESERVED"
        and failure["failure"].endswith("T2 host route/order/binding"),
        "original failure",
    )
    before = validate(capture / "before-t2.json", BEFORE)
    cur, head = fd.read_journal(capture / "raw/events.pfj")
    old, oldhead = fd.read_journal(prior / "raw/events.pfj")
    check(head["journal_sha256"] == CURRENT and oldhead["journal_sha256"] == HIST, "journals")
    cut = before["records"]
    prefix = cur[:cut]
    check(
        before["bytes"] == cut * fd.RECORD.size and audit.record_digest(prefix) == before["sha256"],
        "T1 cut",
    )
    summary = audit.capture_prefix(prefix)
    check(
        summary == validate(capture / "before-t2-candidates.json", before["candidate_file_sha256"]),
        "causal seal",
    )
    offset = summary["t1_calls"]
    tail = cur[cut:]
    check(
        tail[0].kind == 1 and tail[0].call == offset + 1 and tail[0].a == 5,
        "second request boundary",
    )
    current_grade = audit.conservation(cur, head, None, offset + 1)
    earlier = fd.audit(old, oldhead)
    check(earlier["status"] == "PASS", "prior conservation")
    a = audit.authority_projection(tail, offset + 1)
    b = audit.authority_projection(old, 1)
    groups = {key: comparison(a[key], b[key]) for key in a}
    check(not groups["host"]["ordered_equal"], "did not reproduce historical FAIL")
    kinds = {}
    private = {}
    for kind in sorted({row[0] for values in (a, b) for v in values.values() for row in v}):
        axis = "host" if kind in FIELD else "publication" if kind == 17 else "dispatch"
        left = [r for r in a[axis] if r[0] == kind]
        right = [r for r in b[axis] if r[0] == kind]
        label = fd.NAMES[kind]
        kinds[label] = comparison(left, right)
        if left != right:
            private[label] = first_change(left, right)
        if kind in (10, 11, 12):
            for nm, nfields in (("logical", 6), ("slot", 7), ("generation", 8)):
                kinds[f"{label}_{nm}"] = comparison(
                    [r[:nfields] for r in left], [r[:nfields] for r in right]
                )
    for k in a:
        if a[k] != b[k]:
            private[k] = first_change(a[k], b[k])
    geom = {(r.call - offset, r.tile): (r.b, r.c) for r in tail if r.kind == 3}
    ranks = rank_comparison(
        [r for r in a["host"] if r[0] == 27], [r for r in b["host"] if r[0] == 27], geom
    )
    prior_slots, prior_q, _ = audit.state_before(
        [r for r in old if r.kind == 5 or (r.kind == 6 and r.b == 1)]
    )
    slots_equal = summary["slots_at_t2_sha256"] == audit.digest(prior_slots)
    fifo_equal = summary["queued_at_t2_sha256"] == audit.digest(prior_q)
    bounds = [c for c in current_grade["calls"][offset:]]
    times_equal = [(c["positions"], c["tokens"], c["tiles"]) for c in bounds] == [
        (c["positions"], c["tokens"], c["tiles"]) for c in earlier["calls"]
    ]
    return dict(
        status="DIAGNOSED_ORIGINAL_FAIL",
        new_gate_pass=False,
        original_reason=failure["failure"],
        sources=dict(
            capture=FAIL,
            before_t2=BEFORE,
            current=CURRENT,
            prior=HIST,
            auditor=AUDIT,
            program=sha(Path(__file__)),
        ),
        conservation_pass=True,
        fd_restat_in_diagnostic=False,
        slots_equal=slots_equal,
        slot_count=len(prior_slots),
        initial_queue_equal=fifo_equal,
        geometry_and_positions_equal=times_equal,
        t1_calls=offset,
        t2_calls=len(bounds),
        rank_rows=ranks,
        projections=groups,
        event_class=kinds,
    ), private


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("capture-dir", "prior-on-dir", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    ar = p.parse_args()
    ar.new_output_dir.mkdir(mode=0o700)
    try:
        receipt, detail = run(ar.capture_dir, ar.prior_on_dir)
        save(ar.new_output_dir / "first-private.json", detail)
        receipt["private_first_sha256"] = sha(ar.new_output_dir / "first-private.json")
    except (ValueError, IndexError, KeyError, OSError, TypeError) as exc:
        receipt = dict(status="FAIL_DIAGNOSTIC_PRESERVED", error=str(exc))
    save(ar.new_output_dir / "receipt.json", receipt)
    print(receipt["status"])
    return int(receipt["status"] != "DIAGNOSED_ORIGINAL_FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
