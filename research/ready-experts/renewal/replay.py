"""Price T2 victim renewal and the first acquisition that any demand-only bank must serve."""

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LAYER = HERE.parent / "layer"
CC = run_path(LAYER / "client_cost.py")
C, B, SRC, need = (CC[k] for k in ("C", "B", "SRC", "need"))
A = CC["A"]
R = C["R"]
Job, Region = R["Job"], C["Region"]
QUAL = HERE.parents[1] / "qualification-retake"
EXCLUSIVE = QUAL / "phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/exclusive_bank"
Bank = run_path(EXCLUSIVE / "screen.py")["Bank"]
METHOD = "34d2bd105e6cd00dd50007bd6ab72aead04268b0791fcac745ee613b26e6e92a"
PARENT = "96a66cb940d5fa7609e415eda989e980c28bdfe985074791ac7fed7a07969ae0"
CAP = R["BUDGET"]
PAYLOAD = R["PAYLOAD"]
WINDOW = 13221888


@dataclass(frozen=True)
class Transfer:
    key: tuple
    price: Job
    mandatory: bool
    fixed_hit: bool
    renewal_hit: bool


def first_acquisitions(records, available):
    """Relax capacity forever and ordering within this region. A free job can serve its peers."""
    by_key = defaultdict(list)
    for record in records:
        by_key[record.price.expert].append(record)
    forced = []
    for key, group in sorted(by_key.items()):
        if key not in available and all(r.mandatory for r in group):
            forced.append(
                Job(key, min(r.price.read_ns for r in group), min(r.price.set_ns for r in group))
            )
    available.update(by_key)
    return forced


def ledger(rows, waves, seed):
    initial = SRC["Q"]["bindings"](rows)
    slots = {
        loc: (expert, gen, state)
        for loc, (expert, gen, state, claim) in initial.items()
        if not claim and state == 2
    }
    primary = {(layer, expert) for (layer, _), (expert, _, _) in slots.items()}
    need(len(slots) == len(primary) == 1440, "initial primary ownership")
    seed_set = set(seed)
    bank = Bank(CAP, seed, primary)
    mandatory = {k: cost for w in waves for k, cost in w.required_service.items()}
    decisions = {}
    reads = {}
    sets = defaultdict(list)
    published = set()
    volumes = defaultdict(lambda: defaultdict(Counter))
    for e in rows:
        k = SRC["key"](e)
        loc = (e.layer, e.slot)
        if e.kind == 11:
            old, gen, state = slots[loc]
            need(
                state == 2 and e.a == old and e.gen == gen + 1 and k not in decisions,
                "victim generation",
            )
            incoming = (e.layer, e.expert)
            hit, evicted = bank.reserve(incoming, (e.layer, old))
            fixed = incoming in seed_set
            site = (e.call, e.tile, e.layer)
            decisions[k] = (site, fixed, hit, evicted)
            slots[loc] = (e.expert, e.gen, 1)
            tier = "CPU" if e.layer < 25 else "CUDA0"
            v = volumes[B["phase"](e.call)][tier]
            v.update(
                reservations=1,
                mandatory=int(k in mandatory),
                fixed_hits=int(fixed),
                renewed_hits=int(hit),
                new_hits=int(hit and not fixed),
                lost_hits=int(fixed and not hit),
                victims_demoted=1,
                evictions=int(evicted is not None),
                renewed_pack_requested_bytes=int(not hit) * WINDOW,
                fixed_pack_requested_bytes=int(not fixed) * WINDOW,
                demoted_payload_bytes=PAYLOAD,
                promoted_payload_bytes=int(hit) * PAYLOAD,
            )
        elif e.kind == 30:
            need(
                k in decisions
                and k not in reads
                and e.b == e.c == WINDOW
                and not e.error
                and 0 < e.begin <= e.ns,
                "full unique READ",
            )
            reads[k] = e.ns - e.begin
        elif e.kind == 16:
            need(
                k in reads
                and e.component == len(sets[k]) < 3
                and e.a * 3 == PAYLOAD
                and 0 < e.begin <= e.ns,
                "SET role and extent",
            )
            sets[k].append(e.ns - e.begin)
        elif e.kind == 17:
            need(
                k in decisions
                and k not in published
                and slots[loc] == (e.expert, e.gen, 1)
                and len(sets[k]) == 3,
                "publication before components or stale owner",
            )
            slots[loc] = (e.expert, e.gen, 2)
            published.add(k)
    need(
        len(decisions) == 2354
        and decisions.keys() == published == sets.keys() == reads.keys()
        and len(mandatory) == 1918
        and all(v[2] == 2 for v in slots.values()),
        "final drain",
    )
    need(
        bank.primary == {(layer, expert) for (layer, _), (expert, _, _) in slots.items()}
        and not bank.primary & bank.lru.keys()
        and len(bank.lru) <= CAP,
        "exclusive final ownership",
    )
    groups = defaultdict(list)
    binding = hashlib.sha256()
    for k, (site, fixed, hit, evicted) in decisions.items():
        price = Job((k[0], k[3]), reads[k], sum(sets[k]))
        if k in mandatory:
            need(price.read_ns + price.set_ns == mandatory[k], "same compulsory service price")
        groups[site].append(Transfer(k, price, k in mandatory, fixed, hit))
        binding.update(
            json.dumps([k, site, fixed, hit, evicted], separators=(",", ":")).encode() + b"\n"
        )
    return (
        groups,
        primary,
        dict(volumes),
        {
            "starting_slots": bank.initial,
            "peak_slots": bank.peak,
            "ending_slots": len(bank.lru),
            "initial_duplicates_removed": len(seed) - bank.initial,
            "semantic_reservations_sha256": binding.hexdigest(),
        },
    )


def arm_data(rows, seed):
    waves, _ = SRC["timeline"](rows)
    groups, initial, volumes, ownership = ledger(rows, waves, seed)
    host = SRC["NATIVE"]["host_trace"](rows)
    template = C["partition"](host["calls"], waves, defaultdict(dict))
    cases = defaultdict(list)
    forced_counts = Counter()
    available = set(initial)
    seen_sites = set()
    for number, regions, edges in template:
        block = defaultdict(list)
        for region in regions:
            need(region.site not in seen_sites, "region repeated")
            seen_sites.add(region.site)
            records = groups.get(region.site, [])
            first = first_acquisitions(records, available)
            block["unlimited"].append(Region(region.site, region.internal, first))
            forced_counts[B["phase"](number)] += len(first)
            for name, field in (("fixed", "fixed_hit"), ("renewed", "renewal_hit")):
                for mode in ("copied", "direct"):
                    jobs = []
                    for r in records:
                        if not r.mandatory:
                            continue
                        hit = getattr(r, field)
                        jobs.append(
                            Job(
                                r.price.expert,
                                0 if hit else r.price.read_ns,
                                0 if hit and mode == "direct" else r.price.set_ns,
                            )
                        )
                    block[name + "_" + mode].append(Region(region.site, region.internal, jobs))
        for name, gs in block.items():
            cases[name].append((number, gs, edges))
    need(groups.keys() <= seen_sites, "orphaned reservation")
    return cases, {
        "by_phase_and_tier": volumes,
        "first_compulsory_keys": dict(forced_counts),
        **ownership,
    }


def run(archive, out, existing):
    need(SRC["digest"](HERE / "protocol.md") == METHOD, "frozen method")
    parent = SRC["pinned"](LAYER / "evidence/decision.json", PARENT)
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    need(prior["P106"]["pre_stream_allowance_ns"] == CC["CREDIT"], "frozen client interval")
    root = archive / "part-106" / SRC["SOURCES"]["P106"][0]
    train = run_path(HERE.parent / "selection.py")["train"](root / "ON")
    seal, rows106, _, _ = SRC["Q"]["read_new"](root, SRC["SOURCES"]["P106"][1])
    seeds = {k: [tuple(e) for e in v["ordered_keys"]] for k, v in seal["banks"].items()}
    seeds["publication"] = [tuple(e) for e in train["keys"]]
    offered = set(map(tuple, seal["offered_keys"]))
    need(
        len(offered) == 2829
        and all(len(s) == len(set(s)) == CAP and set(s) <= offered for s in seeds.values()),
        "T1 budget and source",
    )
    data = defaultdict(dict)
    details = {}
    identity = None
    cert = json.loads(gzip.decompress(existing.read_bytes())) if existing else {}
    universal = {}
    for label in ("P106", "P97"):
        (_, _, _), auth = B["read_arm"](archive, label, prior[label])
        rows = rows106
        if label == "P97":
            path = archive / "part-97" / SRC["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        cases, details[label] = arm_data(rows, seeds["lru"])
        candidate = (auth["trajectory_sha256"], details[label]["semantic_reservations_sha256"])
        need(identity is None or identity == candidate, "different routing or bank decisions")
        identity = candidate
        for name, regs in cases.items():
            data[name][label] = (regs, auth["outside_calls_ns"])
        universal[label] = {}
        for clock, limit in (("first_final", B["FIRST_LIMIT"]), ("decode", B["DECODE_LIMIT"])):
            regs = [
                g
                for g in cases["unlimited"]
                if (g[0] <= 46 if clock == "first_final" else g[0] >= 3)
            ]
            key = label + "_" + clock
            if not existing:
                cert[key] = A["propose"](regs, offered, True)
            universal[label][clock] = A["verify"](
                regs, offered, auth["outside_calls_ns"][clock], cert[key], direct=True, limit=limit
            )
    need(len(cert) == 4, "certificate domain")
    checks = {k: CC["assess"](rows, set(), False) for k, rows in data.items() if k != "unlimited"}
    expected = parent["causal_controls"]["results"]["lru"]
    need(
        all(checks["fixed_direct"][k] == expected[k] for k in checks["fixed_direct"]),
        "parent first-final and decode clocks",
    )
    oracle = {k: CC["assess"](data["unlimited"], set(seed), True) for k, seed in seeds.items()}
    for label in data["unlimited"]:
        for clock in ("first_final", "decode"):
            perfect = oracle["lru"]["with_full_client_cost_ns"][label][clock]
            need(
                universal[label][clock]["floor_ns"]
                <= min(x["with_full_client_cost_ns"][label][clock] for x in oracle.values())
                and perfect <= checks["renewed_direct"]["with_full_client_cost_ns"][label][clock],
                "lower bound excludes a feasible assignment",
            )
    if not existing:
        raw = gzip.compress((json.dumps(cert, separators=(",", ":")) + "\n").encode(), mtime=0)
        (out / "proof.json.gz").write_bytes(raw)
    else:
        raw = existing.read_bytes()
    return {
        "schema": "tesy.ready_bank_renewal.v1",
        "status": "TRACE_DERIVED",
        "protocol_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "parent_sha256": PARENT,
        "proof_sha256": hashlib.sha256(raw).hexdigest(),
        "arms": details,
        "causal": checks,
        "unlimited_after_t2_starts": oracle,
        "universal_initial_selection": universal,
        "decisions": {
            "exclusive_even_with_grant": "HEADROOM_ONLY"
            if checks["renewed_direct"]["fits_with_grant"]
            else "NO_GO",
            "all_retention_from_each_seed_even_with_grant": {
                k: "INCONCLUSIVE" if v["fits_with_grant"] else "NO_GO" for k, v in oracle.items()
            },
            "all_initial_and_later_policies_even_with_grant": "NO_GO"
            if any(
                m[clock]["floor_ns"]
                > (limit + (CC["CREDIT"] if label == "P106" and clock == "first_final" else 0))
                for label, m in universal.items()
                for clock, limit in (
                    ("first_final", B["FIRST_LIMIT"]),
                    ("decode", B["DECODE_LIMIT"]),
                )
            )
            else "INCONCLUSIVE",
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    parser.add_argument("--verify", type=Path)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        report = run(a.archive, a.new_output_dir, a.verify)
    except FileNotFoundError as exc:
        path = Path(exc.filename).resolve()
        report = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if path.is_relative_to(a.archive.resolve())
            else "FAIL",
            "missing": path.name,
        }
    except (ValueError, AssertionError, KeyError, OSError, TypeError, ImportError) as exc:
        report = {"status": "FAIL", "reason": str(exc)}
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(report["status"], report.get("decisions", report.get("reason", "")))
    raise SystemExit(report["status"] != "TRACE_DERIVED")
