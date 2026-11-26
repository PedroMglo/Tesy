"""Two processes: select strictly within T1, then replay the actual subsequent T2."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "58c3bf4dc72b93ac533fc8e68ddbbc51c1927b8a6a3379f136fd7ef980c55b8d"
spec = importlib.util.spec_from_file_location("same_t2", HERE.parent / "t1_victims/screen.py")
t2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2)
audit = t2.module(HERE.parent / "t1_capture/audit.py", "same_t1")
need, K, B = t2.need, 353, t2.T


class Admission:
    def __init__(self, capacity, selective):
        self.capacity = capacity
        self.selective = selective
        self.bank = {}
        self.stats = {"cpu": Counter(), "cuda": Counter()}

    def offer(self, key, scores, sequence):
        stat = self.stats[audit.key_tier(key)]
        stat["offers"] += 1
        if key in self.bank:
            self.bank[key] = sequence
            stat["refreshes"] += 1
            return
        if len(self.bank) == self.capacity:
            if self.selective:
                victim = min(self.bank, key=lambda e: (scores[e], self.bank[e], e))
                if scores[key] <= scores[victim]:
                    stat["refused"] += 1
                    return
            else:
                victim = min(self.bank, key=self.bank.__getitem__)
            del self.bank[victim]
            self.stats[audit.key_tier(victim)]["discarded_in_t1"] += 1
        self.bank[key] = sequence
        stat["installs"] += 1
        need(len(self.bank) <= self.capacity, "instantaneous L2 capacity")

    def result(self):
        keys = sorted(self.bank, key=self.bank.__getitem__)
        for tier, stat in self.stats.items():
            stat["surviving"] = sum(audit.key_tier(k) == tier for k in keys)
            need(stat["installs"] == stat["surviving"] + stat["discarded_in_t1"], "T1 conservation")
            need(stat["offers"] == stat["refused"] + stat["installs"] + stat["refreshes"], "offers")
            stat["install_bytes"] = stat["installs"] * B
        return dict(
            ordered_keys=list(map(list, keys)),
            ordered_keys_sha256=audit.digest(keys),
            tier=self.stats,
        )


def select(rows, capacity=K):
    slots = {}
    scores = Counter()
    seen = set()
    votes = Counter()
    banks = {name: Admission(capacity, name == "votes") for name in ("recency", "votes")}
    for index, r in enumerate(rows):
        slot = (r.layer, r.slot)
        if r.kind == 5:
            need(slot not in slots and r.a in (0, 1, 2), "invalid snapshot")
            slots[slot] = (r.gen, r.expert, r.a)
        elif r.kind == 27:
            ids = tuple((r.a >> (8 * i)) & 255 for i in range(4))
            need(
                0 <= r.layer < 36 and 0 <= r.a < 2**32 and len(set(ids)) == 4 and max(ids) < 128,
                "target top four",
            )
            scores.update((r.layer, e) for e in ids)
            votes[audit.key_tier((r.layer, 0))] += 4
        elif r.kind == 11:
            gen, old, state = slots[slot]
            need(state in (0, 2) and r.gen == gen + 1 and old == r.a, "victim/slot generation")
            if state == 2:
                key = (r.layer, old)
                seen.add(key)
                for bank in banks.values():
                    bank.offer(key, scores, index)
            slots[slot] = (r.gen, r.expert, 1)
        elif r.kind == 17:
            need(slots[slot] == (r.gen, r.expert, 1), "publication")
            slots[slot] = (r.gen, r.expert, 2)
    return dict(
        votes=dict(votes),
        distinct_victims=audit.per_tier(seen),
        banks={key: bank.result() for key, bank in banks.items()},
    )


def blob_hash(blob):
    return hashlib.sha256(blob).hexdigest()


def get_prefix(a):
    """Read exactly N records of the journal, never its post-seal suffix."""
    capture = t2.host.pinned(a.capture_dir / "receipt.json", a.capture_sha256)
    need(
        capture["status"] == "PASS_T1_VICTIM_WINDOW_AND_T2_REFERENCE"
        and capture["prior_on_sha256"] == t2.PRIOR,
        "validated natural family",
    )
    seal = t2.host.pinned(a.capture_dir / "before-t2.json", capture["before_t2_sha256"])
    actual = t2.host.pinned(
        a.capture_dir / "before-t2-candidates.json", seal["candidate_file_sha256"]
    )
    n = seal["records"]
    need(0 < n < 262144 and seal["bytes"] == n * t2.fd.RECORD.size, "T1 extent")
    with (a.capture_dir / "raw/events.pfj").open("rb") as f:
        header = t2.fd.HEADER.unpack(f.read(t2.fd.HEADER.size))
        need(
            header[:4] == (b"TESYPF1\0", 1, 96, 262144)
            and header[4] == header[5] > n
            and header[6:] == (1, 0),
            "sealed journal",
        )
        data = f.read(seal["bytes"])
    need(len(data) == seal["bytes"] and blob_hash(data) == seal["sha256"], "T1 prefix digest")
    rows = [t2.fd.Row(*v) for v in t2.fd.RECORD.iter_unpack(data)]
    need(audit.capture_prefix(rows) == actual, "reference T1")
    result = select(rows)
    ref = actual["capacities"]["353"]
    need(result["banks"]["recency"]["ordered_keys"] == ref["ordered_keys"], "recency bank order")
    for s in ("cpu", "cuda"):
        need(
            result["banks"]["recency"]["tier"][s]["installs"]
            == ref["cold_start_copies_by_tier"][s],
            "recency cost",
        )
    return result | dict(
        prefix_sha256=seal["sha256"],
        capture_sha256=a.capture_sha256,
        protocol_sha256=PROTOCOL,
        method_sha256=t2.host.sha(Path(__file__)),
    )


def score(a):
    sealed = t2.host.pinned(a.selection_dir / "receipt.json", a.selection_sha256)
    selected = t2.host.pinned(a.selection_dir / "banks.json", sealed["banks_sha256"])
    need(
        sealed["status"] == "PASS_CAUSAL_VICTIM_SELECTION"
        and selected["capture_sha256"] == a.capture_sha256
        and selected["protocol_sha256"] == PROTOCOL
        and selected["method_sha256"] == t2.host.sha(Path(__file__)),
        "T1-only selection",
    )
    inputs = t2.prepare_inputs(a)
    out = {}
    rec = t2.host.pinned(a.recency_receipt, a.recency_sha256)
    need(
        rec["status"] == "PASS" and rec["sources"]["capture"] == a.capture_sha256,
        "independent sealed recency replay",
    )
    for name, bank in selected["banks"].items():
        keys = [tuple(k) for k in bank["ordered_keys"]]
        need(
            len(keys) == len(set(keys)) == K and audit.digest(keys) == bank["ordered_keys_sha256"],
            "qualified full bank",
        )
        selection = {
            "capacities": {
                "239": {"identified": False},
                "353": {"identified": True, "ordered_keys": bank["ordered_keys"]},
            }
        }
        observed = inputs.capture["rows"][1]
        table = t2.analyse_arm(
            inputs.tail, observed, inputs.raw_now, inputs.meta, selection, inputs.current_mem
        )
        row = next(
            r for r in table["arms"] if r["k"] == K and r["family"] == "victims" and r["warm"]
        )
        if name == "recency":
            ref = next(
                r
                for r in rec["current"]["arms"]
                if r["k"] == K and r["family"] == "victims" and r["warm"]
            )
            need(row == ref, "recency control")
        model = t2.Policy("victims", K, keys)
        check = t2.simulate(inputs.tail, model)
        need(
            (check["decode_hits"], check["remaining_prefill_bytes"])
            == (row["decode_hits"], row["remaining_prefill_bytes"]),
            "same finite comparator",
        )
        tier = {}
        for origin, stat in bank["tier"].items():
            initial = model.victims.stats["initial_" + origin]
            used = initial["reused_installs"]
            need(0 <= used <= stat["surviving"] == initial["copies_of_victims"], "initial copies")
            tier[origin] = stat | {
                "used_in_t2": used,
                "unused_through_t2": stat["installs"] - used,
                "unused_copy_bytes": B * (stat["installs"] - used),
            }
        out[name] = dict(
            selection_sha256=bank["ordered_keys_sha256"],
            t1_costs=tier,
            t2=row,
            budgets=table["budgets"],
        )
    return dict(
        status="PASS_SAME_CAPACITY_AND_T2_REPLAY",
        arms=out,
        votes=selected["votes"],
        distinct_victims=selected["distinct_victims"],
        protocol_sha256=PROTOCOL,
        sources=inputs.sources,
        causal_selection_receipt_sha256=a.selection_sha256,
        recency_control_sha256=a.recency_sha256,
    )


def save(path, payload):
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    need(len(data) <= 512 * 1024, "output size")
    with path.open("xb") as f:
        f.write(data)
    return blob_hash(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="mode", required=True)
    for which in ("select", "score"):
        q = commands.add_parser(which)
        for opt in ("capture-dir", "new-output-dir"):
            q.add_argument("--" + opt, type=Path, required=True)
        q.add_argument("--capture-sha256", required=True)
        if which == "score":
            for opt in (
                "prior-on-dir",
                "plan-dir",
                "inventory",
                "selection-dir",
                "recency-receipt",
            ):
                q.add_argument("--" + opt, type=Path, required=True)
            for opt in ("current-result-sha256", "selection-sha256", "recency-sha256"):
                q.add_argument("--" + opt, required=True)
    a = p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        need(t2.host.sha(HERE / "protocol.md") == PROTOCOL, "selection protocol")
        if a.mode == "select":
            result = get_prefix(a)
            digest = save(a.new_output_dir / "banks.json", result)
            receipt = dict(
                status="PASS_CAUSAL_VICTIM_SELECTION",
                banks_sha256=digest,
                prefix_sha256=result["prefix_sha256"],
                capture_sha256=a.capture_sha256,
            )
        else:
            receipt = score(a)
    except Exception as err:
        receipt = {"status": "FAIL_PRESERVED", "error_type": type(err).__name__}
        (a.new_output_dir / "error.txt").write_text(str(err) + "\n")
    print(receipt["status"], save(a.new_output_dir / "receipt.json", receipt))
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
