"""Test one fixed balance of prefill frequency and victim recency on the two packed turns."""

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE.parent / "request_cost/score.py"))
Q, check, pinned, digest = (S[k] for k in ("Q", "check", "pinned", "digest"))
CAP, PAYLOAD = Q["CAP"], Q["SIZE"]
HISTORY = "340b3dfa3d0e3979c83875f309873c8f42b554fb6c7b11f27a6de275a978ef19"
PROTOCOL = "101f9a0abb2bcf2cd124529759f8778442bbd1d379f7d299109761ec07731045"


class SplitBank:
    def __init__(self, capacity, protected):
        if not 0 <= protected <= capacity or capacity < 1:
            raise ValueError("invalid protected quota")
        self.capacity, self.protected = capacity, protected
        self.held, self.frequency, self.copies = {}, Counter(), Counter()
        self.offers = self.repeated = self.rejected = self.evictions = 0

    def rank(self, layer, ids):
        if (
            not 0 <= layer < 36
            or len(ids) != 4
            or len(set(ids)) != 4
            or not all(e in range(128) for e in ids)
        ):
            raise ValueError("invalid top-4")
        self.frequency.update((layer, e) for e in ids)

    def offer(self, key):
        self.offers += 1
        if key in self.held:
            del self.held[key]
            self.held[key] = self.offers
            self.repeated += 1
            return
        self.held[key] = self.offers
        if len(self.held) > self.capacity:
            protected = set(
                sorted(self.held, key=lambda k: (self.frequency[k], self.held[k], k), reverse=True)[
                    : self.protected
                ]
            )
            # Insertion order is last-offer order, including the candidate.
            victim = next(k for k in self.held if k not in protected)
            del self.held[victim]
            if victim == key:
                self.rejected += 1
                return
            self.evictions += 1
        self.copies["CPU" if key[0] < 25 else "CUDA0"] += 1

    def summary(self):
        copies = sum(self.copies.values())
        check(
            self.offers == copies + self.rejected + self.repeated
            and copies - self.evictions == len(self.held) <= self.capacity,
            "bank conservation",
        )
        return dict(
            offers=self.offers,
            repeated=self.repeated,
            rejected=self.rejected,
            evictions=self.evictions,
            held=len(self.held),
            copies={k: self.copies[k] for k in ("CPU", "CUDA0")},
        )


def select(pfj, prefix):
    cut, _ = Q["PROFILE"]["metadata"](pfj, True)
    banks = {k: SplitBank(CAP, v) for k, v in (("lru", 0), ("mixed", 176), ("prefill", CAP))}
    calls = set(prefix["prefill_calls"])
    # read_new independently replays slot generations and authenticates this exact pre-POST cut.
    for row in Q["PROFILE"]["iter_rows"](pfj, 0, cut):
        if row.kind == 27 and row.call in calls:
            for bank in banks.values():
                bank.rank(row.layer, row.a.to_bytes(4, "little"))
        elif row.kind == 11 and row.a >= 0:
            for bank in banks.values():
                bank.offer((row.layer, row.a))
    for name in ("lru", "prefill"):
        expected = prefix["banks"][name]
        ordered = [list(key) for key in banks[name].held]
        check(banks[name].summary() | {"ordered_keys": ordered} == expected, "endpoint " + name)
    return banks


def review_cost(analysis, previous):
    for key in previous.keys() - {"policies"}:
        check(analysis[key] == previous[key], "historical observation: " + key)
    for name, control in previous["policies"].items():
        for scope, old in control.items():
            new = analysis["policies"][name][scope]
            check(
                old["distinct_hit_keys"] == new["distinct_hit_keys"]
                and old["before_client_in_tail_ns"] == new["client_tail_extra_ns"]
                and (old["phases"] is None or old["phases"] == new["phases"]),
                "phase control",
            )
            for price, expected in old["scenarios"].items():
                check({k: new["cost"][price][k] for k in expected} == expected, "clock control")
    result = {}
    for name in ("lru", "mixed", "prefill"):
        policy = analysis["policies"][name]
        phases = policy["drained"]["phases"]
        volumes = {}
        for phase, group in phases.items():
            volumes[phase] = {}
            for tier in ("CPU", "CUDA0"):
                count, hits = group["jobs_" + tier], group.get("hits_" + tier, 0)
                check(0 <= hits <= count, "bank cannot supply unrequested bytes")
                volumes[phase][tier] = dict(
                    reservations=count,
                    hits=hits,
                    bank_payload_B=hits * PAYLOAD,
                    source_payload_B=(count - hits) * PAYLOAD,
                )
        result[name] = dict(
            volumes=volumes,
            costs={
                scope: {
                    price: {
                        k: v[k]
                        for k in (
                            "remaining_first_ns",
                            "remaining_decode_ns",
                            "margin_first_ns",
                            "margin_decode_ns",
                            "joint",
                        )
                    }
                    for price, v in scores["cost"].items()
                }
                for scope, scores in policy.items()
            },
        )
    return result


def run(a):
    check(digest(HERE / "protocol.md") == PROTOCOL, "prospective protocol")
    prior = pinned(HERE.parent / "request_cost/receipt.json", HISTORY)
    check(
        digest(HERE.parent / "request_cost/score.py") == prior["source_sha256"], "historical method"
    )
    for label, root in (("P97", a.p97), ("P106", a.p106)):
        name, _, anchor = S["SOURCES"][label]
        check(root.name == name, "observer family")
        manifest = pinned(a.archive / ("part-" + label[1:]) / "manifest.json", anchor)
        S["authenticate_raw"](root, manifest, ["raw/T2-result.json", "raw/T2-request.jsonl"])
    _, sha106, _ = S["SOURCES"]["P106"]
    sealed, rows, tiers, source = Q["read_new"](a.p106, sha106)
    banks = select(a.p106 / "ON/observer/events.pfj", sealed)
    selection = {k: set(b.held) for k, b in banks.items()}
    _, strict, _ = Q["read_current"](rows, tiers)
    summaries = {}
    for name, bank in banks.items():
        pairs = list(bank.held)
        summary = bank.summary()
        check(
            set(pairs) <= set(map(tuple, sealed["offered_keys"])) and len(pairs) == CAP,
            "ineligible victim or missing slot",
        )
        summaries[name] = summary | dict(
            selected_sha256=hashlib.sha256(
                json.dumps(pairs, separators=(",", ":")).encode()
            ).hexdigest(),
            first_use_hits=Q["tier_counts"](set(pairs) & strict.keys(), tiers),
            acquisition_B={k: count * PAYLOAD for k, count in summary["copies"].items()},
        )
    arm = a.p106 / "ON"
    family = pinned(a.p106 / "family.json", sha106)
    link = pinned(arm / "arm.json", family["arms"]["ON"]["sha256"])
    receipt = pinned(arm / "receipt.json", link["receipt_sha256"])
    start = json.loads((arm / "raw/T2-result.json").read_bytes())["request_started_monotonic"]
    delay = receipt["full_prefix"]["post_entry_ns"][1] - int(Decimal(str(start)) * 10**9)
    current, jobs = S["assess"](a.p106, receipt, rows, tiers, selection, delay)
    _, _, old, audit = S["CHAIN"]["chain"](a.p97, S["SOURCES"]["P97"][1])
    again = S["NATIVE"]["audit_arm"](a.p97 / "ON", old, old["pack_events"]["before_second_ns"])
    check(
        json.loads(json.dumps(again)) == audit and audit["jobs"]["eligible_clean_run"],
        "P97 service",
    )
    old_rows, header = S["T"]["PFJ"]["read_journal"](a.p97 / "ON/raw/events.pfj")
    previous, old_jobs = S["assess"](a.p97, old, old_rows, tiers, selection, 0)
    check(
        header["journal_sha256"] == prior["P97_journal_sha256"]
        and old_jobs == jobs
        and Q["bindings"](old_rows) == Q["bindings"](rows)
        and old["trajectories"] == receipt["trajectories"]
        and previous["route"] == current["route"],
        "different target work",
    )
    clocks = {
        key: review_cost(result, prior[key])
        for key, result in (("P97", previous), ("P106", current))
    }
    gates = {
        "at_least_83_prefill_cpu_first_uses": summaries["mixed"]["first_use_hits"]["CPU"] >= 83,
        "at_least_92_decode_cpu_hits": all(
            sum(v["mixed"]["volumes"][ph]["CPU"]["hits"] for ph in ("decode_first", "decode_tail"))
            >= 92
            for v in clocks.values()
        ),
        "less_T1_acquisition_than_recency": sum(banks["mixed"].copies.values())
        < sum(banks["lru"].copies.values()),
        "positive_decode_margin_both_drained_free": all(
            v["mixed"]["costs"]["drained"]["free"]["margin_decode_ns"] > 0 for v in clocks.values()
        ),
    }
    return dict(
        decision="GO_FIXTURE_ONLY" if all(gates.values()) else "NO_GO_FIXED_QUOTA",
        evidence="TRACE_DERIVED",
        gates=gates,
        T1=summaries,
        T2=clocks,
        source=source,
        payload_B=PAYLOAD,
        route=current["route"],
        jobs=len(jobs),
        control_sha256=HISTORY,
        protocol_sha256=digest(HERE / "protocol.md"),
        code_sha256=digest(Path(__file__)),
        model_starts=0,
        generation_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive", "p97", "p106", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        receipt = run(a)
    except Exception as exc:
        receipt = dict(decision="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    with (out / "receipt.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(receipt["decision"], receipt.get("reason", ""))
    raise SystemExit(receipt["decision"] == "FAIL_PRESERVED")
