"""Compare selection from past victim offers to a future-informed witness of equal capacity."""

import argparse
import hashlib
import itertools
import json
from collections import Counter
from fractions import Fraction
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
J = run_path(str(HERE / "joint.py"))
B, ENV, HTTP, G, need, save = (J[k] for k in ("BANK", "ENV", "HTTP", "G", "need", "save"))
CAP = B["MIX"]["CAP"]
METHOD = "4ce9dc8fc8071cbc9b7266a2ffe1e6793d132ffa24eb3ce257515d354ea24e48"
JOINT = "730ca17f999f9b5de4739675bba6e2232f44334638be9686961588158205972f"


class OfferBank:
    def __init__(self, capacity):
        self.cap = capacity
        self.counts = Counter()
        self.last = {}
        self.held = set()
        self.copies = Counter()
        self.evicted = 0

    def rank(self, k):
        return self.counts[k], self.last[k], k

    def offer(self, k, index):
        self.counts[k] += 1
        self.last[k] = index
        if k in self.held:
            return
        if len(self.held) == self.cap:
            victim = min(self.held, key=self.rank)
            if self.rank(k) < self.rank(victim):
                return
            self.held.remove(victim)
            self.evicted += 1
        self.held.add(k)
        self.copies["CPU" if k[0] < 25 else "CUDA0"] += 1


def fixture():
    for stream in itertools.product(range(3), repeat=4):
        bank = OfferBank(2)
        for i, v in enumerate(stream):
            before = bank.held.copy()
            k = (0, v)
            bank.offer(k, i)
            expected = sorted(bank.counts, key=bank.rank, reverse=True)[:2]
            need(
                bank.held == set(expected)
                and bank.held - before <= {k}
                and sum(bank.copies.values()) - bank.evicted == len(bank.held),
                "online admission",
            )
    return 3**4


def offered(a):
    q = B["B"]["Q"]
    name, pin, _ = B["B"]["C"]["SOURCES"]["P106"]
    root = a.archive / "part-106" / name
    sealed, _, _, _ = q["read_new"](root, pin)
    pfj = root / "ON/observer/events.pfj"
    count, _ = q["PROFILE"]["metadata"](pfj, True)
    seq = [
        (r.layer, r.a)
        for r in q["PROFILE"]["iter_rows"](pfj, 0, count)
        if r.kind == 11 and r.a >= 0
    ]
    need(
        len(seq) == 4548 and set(seq) == set(map(tuple, sealed["offered_keys"])),
        "T1-only observations",
    )
    ctl = sealed["banks"]["lru"]
    return seq, [tuple(k) for k in ctl["ordered_keys"]], ctl["copies"]


def signature(keys):
    return hashlib.sha256(json.dumps(sorted(keys), separators=(",", ":")).encode()).hexdigest()


def study(a):
    commit, tree = G["tree"](G["REPO"])
    need(
        commit == a.commit and J["AUDIT"]["sha"](HERE / "offers-protocol.md") == METHOD,
        "sealed method",
    )
    joint = G["read"](HERE / "joint-result.json", JOINT)
    envelope = G["read"](HERE / "envelope-result.json", B["ENVELOPE"])
    physical = G["read"](HERE / "http-result.json", envelope["four_arm_review_sha256"])
    HTTP["R"]["reopen"](a.family, physical["family_sha256"])
    ref = G["read"](HERE.parent / "reload-result.json", ENV["RELOADS"])
    slot = G["read"](HERE.parent / "slot-result.json", ENV["SLOTS"])
    controls = fixture()
    seq, lru, lru_copies = offered(a)
    bank = OfferBank(CAP)
    for i, k in enumerate(seq):
        bank.offer(k, i)
    need(
        len(bank.held) == CAP
        and sum(bank.copies.values()) - bank.evicted == CAP
        and set(sorted(bank.last, key=bank.last.get)[-CAP:]) == set(lru),
        "full stream and LRU",
    )
    calls, _, matched = B["generations"](a, ref, slot)
    prefill = {k for k, c in calls.items() if c <= 2}

    def demand(keys):
        return Counter((k[0], k[3]) for k in keys)

    pre, dec = demand(prefill - matched), demand(calls.keys() - prefill)
    weights = pre + dec
    future = set(sorted(bank.last, key=lambda k: (weights[k], bank.last[k], k), reverse=True)[:CAP])
    captured = set()
    future_copies = Counter()
    for k in seq:
        if k in future and k not in captured:
            future_copies["CPU" if k[0] < 25 else "CUDA0"] += 1
            captured.add(k)
    need(captured == future and sum(future_copies.values()) == CAP, "offered payloads only")
    graphs, marks = J["graphs"](a.family, a.lookup_run, 44)
    graph = graphs["serial_reference"]
    old = J["original_paths"](
        envelope["turns"]["T2"]["scenarios"]["serial_reference"], graph, 46, 44
    )
    former = {J["history"](p) for p in old}
    row = physical["arms"]["SERIAL"]["rows"][1]
    factor = J["MILLION"]
    first = (Fraction(str(row["first_final_s"])) - Fraction(str(row["prefill_s"]))) * factor - (
        marks[44] - marks[0]
    )
    decode = Fraction(str(row["decode_s"])) * factor - (marks[-1] - marks[0])
    lower = envelope["serial_nominal_prefill"]["read_bytes"]["min"]
    catalog, results = {}, {}
    for name, keys, copies in (
        ("lru", set(lru), lru_copies),
        ("offer_count", bank.held, bank.copies),
        ("future_volume", future, future_copies),
    ):
        covered = {k for k in calls if (k[0], k[3]) in keys}
        hits = Counter(calls[k] for k in covered - prefill)

        @cache
        def paths_at(ppm, hits=hits):
            return ENV["frontier"](J["repriced"](graph, hits, ppm, 44), 46, 44)

        choices = {}
        for profile, extra in (("no_rescue", set()), ("matched35", matched)):
            union = len((covered & prefill) | extra)
            floor = Fraction(max(0, lower - union * B["WINDOW"]) * factor, B["RATE"])
            out = dict(
                union=union,
                min_prefill_service_s=float(floor / factor),
                **J["solve"](paths_at, first, decode, floor, catalog, former),
            )
            if name == "lru":
                need(out == joint["scenarios"]["lru"]["serial_reference"][profile], "LRU control")
            choices[profile] = out
        results[name] = dict(
            held=len(keys),
            membership_sha256=signature(keys),
            prefill_hits=len(covered & prefill),
            overlap_matched35=len(covered & matched),
            decode_hits=len(covered - prefill),
            T1_acquisition_payload_B={
                tier: copies[tier] * B["B"]["PAYLOAD"] for tier in ("CPU", "CUDA0")
            },
            profiles=choices,
        )
    return dict(
        status="TRACE_DERIVED_OFFER_SELECTION",
        commit=commit,
        tree=tree,
        protocol_sha256=METHOD,
        prior_sha256=JOINT,
        model_starts=0,
        requests=0,
        distinct_offers=len(bank.last),
        offers=len(seq),
        capacity=CAP,
        synthetic_streams=controls,
        separate_top353={
            label: sum(sorted((scores[k] for k in bank.last), reverse=True)[:CAP])
            for label, scores in (("prefill_outside_matched35", pre), ("all_decode", dec))
        },
        paths=catalog,
        scenarios=results,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "family", "lookup-run", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", study(a))
