"""A causal, batch-pinned physical LRU initialized from the pre-POST T1 byte seal."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PRE = HERE.parent
base = run_path(PRE / "screen.py")
check, sha, pinned = (base[k] for k in ("check", "sha", "pinned"))
ORACLE = "097085db812f87c7d4a855edf231aa256066d340e4372a9ba9091ca9b4b1ceef"
NS = 10**9


def digest(obj):
    return hashlib.sha256(
        json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def last_uses(rows):
    # Advance only on DEMAND at the physical CPU, never use wall time or worker order.
    last = {}
    counter = 0
    for r in rows:
        if r.kind == 10 and r.layer < 25:
            check(r.layer >= 0 and 0 <= r.expert < 128, "CPU DEMAND identity")
            counter += 1
            last[128 * r.layer + r.expert] = counter
    return last, counter


def start_clock(archive):
    root = archive / "part-63" / base["front"]["FAMILY_NAME"] / "ON"
    arm = pinned(root / "receipt.json", base["front"]["SEALS"]["arm"])
    info = pinned(root / "before-t2.json", arm["before_t2_sha256"])
    selection = pinned(root / "before-t2-candidates.json", info["candidate_file_sha256"])
    integration = base["NATURAL"].parents[2]
    layout = run_path(integration / "analyse.py")
    reader = layout["RECORD"]
    check(
        0 < info["records"] <= 262144 and info["bytes"] == info["records"] * reader.size,
        "prefix bytes",
    )
    with (root / "raw/events.pfj").open("rb") as f:
        f.seek(layout["HEADER"].size)
        raw = f.read(info["bytes"])
    check(
        len(raw) == info["bytes"] and hashlib.sha256(raw).hexdigest() == info["sha256"],
        "pre-POST T1 seal",
    )
    rows = [layout["Row"](*r) for r in reader.iter_unpack(raw)]
    audit = run_path(integration / "t1_capture/audit.py")
    check(json.loads(json.dumps(audit["capture_prefix"](rows))) == selection, "T1 bank witness")
    slots, queue, _ = audit["state_before"](rows)
    check(not queue and all(s[2] == 2 and s[3] == 0 for s in slots), "non-READY at T2")
    initial = {128 * (i // 40) + s[0] for i, s in enumerate(slots[:1000])}
    bank = {
        128 * owner + e for owner, e in selection["capacities"]["353"]["ordered_keys"] if owner < 25
    }
    last, n = last_uses(rows)
    keys = initial | bank
    clock = {k: last.get(k, 0) for k in keys}
    return (
        initial,
        bank,
        clock,
        n,
        dict(
            prefix_bytes=info["bytes"],
            prefix_sha256=info["sha256"],
            selected_sha256=info["candidate_file_sha256"],
            cpu_demand_events=n,
            identified_entry_ages=sum(v > 0 for v in clock.values()),
            unobserved_cold_ties=sum(v == 0 for v in clock.values()),
            causal_entry_sha256=digest(sorted(clock.items())),
        ),
    )


class LRU:
    def __init__(self, capacity, keys, ages, current):
        check(
            capacity > 0
            and len(keys) <= capacity
            and all(0 <= ages.get(k, 0) <= current for k in keys),
            "entry or ages",
        )
        self.capacity = capacity
        self.ages = {k: ages.get(k, 0) for k in keys}
        self.clock = current

    def serve(self, pins):
        check(
            len(pins) == len(set(pins)) <= self.capacity, "duplicate pins or insufficient capacity"
        )
        incoming = [k for k in pins if k not in self.ages]
        n = max(0, len(self.ages) + len(incoming) - self.capacity)
        victims = (
            sorted(self.ages.keys() - set(pins), key=lambda k: (self.ages[k], k))[:n] if n else []
        )
        check(len(victims) == n, "pinned eviction")
        for k in victims:
            del self.ages[k]
        for k in pins:
            self.clock += 1
            self.ages[k] = self.clock
        return incoming, victims


def simulate(groups, primary, bank, ages, current, name):
    fixed = name != "U1262"
    if name == "P40":
        pools = [LRU(40, {k for k in primary if k // 128 == i}, ages, current) for i in range(25)]
    else:
        pools = [LRU(1000 if fixed else 1262, primary if fixed else primary | bank, ages, current)]
    h = hashlib.sha256()
    end_states = {}
    old = None
    events = []
    for g in groups:
        phase = g["phase"]
        if phase != old and old is not None:
            end_states[old] = digest([sorted(p.ages.items()) for p in pools])
        old = phase
        layer = g["site"][2]
        if layer >= 25:
            events.append(((), ()))
            continue
        incoming, victims = pools[layer if name == "P40" else 0].serve(g["pins"])
        h.update(json.dumps([g["site"], incoming, victims], separators=(",", ":")).encode() + b"\n")
        events.append(
            (
                tuple(k for k in incoming if not fixed or k not in bank),
                tuple(k for k in incoming if fixed and k in bank),
            )
        )
    if old is not None:
        end_states[old] = digest([sorted(p.ages.items()) for p in pools])
    return events, dict(end_sha256_by_phase=end_states, ordered_replacements_sha256=h.hexdigest())


def unknown_budget(chains, total, limit):
    # Each unknown incurs the same x ns; all unknowns of a short callback may overlap.
    # Every chain in the list is the maximum known READ in a callback containing >=1 unknown.
    spare = limit - total
    if spare < 0:
        return dict(status="NO_ROOM_AT_ZERO", wall_margin_ns=spare, max_uniform_ns=None)
    if not chains:
        return dict(status="NO_UNPRICED_READ", wall_margin_ns=spare, max_uniform_ns=None)
    lo = 0
    hi = max(chains) + spare + 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if sum(max(0, mid - y) for y in chains) <= spare:
            lo = mid
        else:
            hi = mid
    return dict(status="FINITE_CONDITIONAL_BUDGET", wall_margin_ns=spare, max_uniform_ns=lo)


def prefill_prices(archive, joint):
    plan = pinned(
        archive / "part-69/tesy-prefill-transport-plan-20261125-r01/plan.json", base["PF_PLAN"]
    )
    schedules = {5: [], 148: []}
    for g in plan["groups"]:
        schedules[g["call_tokens"]].extend((g, j) for j in g["jobs"] if j["source"] == "disk")
    check([len(v) for v in schedules.values()] == [34, 1024], "prefill population")
    review = run_path(base["FRONT"] / "transport/joint/review.py")
    tables = {}
    for i, order in enumerate(("RP", "PR"), 1):
        root = archive / f"part-71/tesy-prefill-bandwidth-20261125-r{i:02d}"
        rec = pinned(root / "receipt.json", joint["raw_receipt_sha256"][i - 1])
        raw = root / "raw/P.jsonl"
        summary = rec["arms"]["P"]
        check(
            rec["status"] == "PASS_PREFILL_FULL_QUEUE_PAIR"
            and rec["order"] == order
            and rec["plan_sha256"] == base["PF_PLAN"]
            and sha(raw) == summary["raw_sha256"],
            "prefill pack price source",
        )
        prices = {}
        with raw.open() as stream:
            for line, (tokens, expected), call in zip(
                stream, schedules.items(), summary["calls"], strict=True
            ):
                row = json.loads(line)
                check(
                    row["call"] == call["call"] == expected[0][0]["call"]
                    and row["call_tokens"] == call["call_tokens"] == tokens,
                    "call order",
                )
                review["inspect_jobs"](row["jobs"], expected, "P", call)
                for rec_job, (g, j) in zip(row["jobs"], expected, strict=True):
                    site = tuple(g[k] for k in ("call", "tile", "layer", "wave"))
                    key = (site, 128 * g["layer"] + j["expert"])
                    check(key not in prices, "duplicate site price")
                    lo, hi = rec_job["read_spans_ns"][0]
                    prices[key] = hi - lo
        check(len(prices) == 1058, "timed prefill jobs")
        tables[order] = prices
    return tables


def prefill_coverage(groups, events, price):
    by_phase = {}
    for g, (disk, _) in zip(groups, events, strict=True):
        tier = "cpu" if g["site"][2] < 25 else "cuda"
        c = by_phase.setdefault(g["phase"], {}).setdefault(tier, Counter())
        keys = disk if tier == "cpu" else g["logical_disk"]
        for k in keys:
            ns = price.get((g["site"], k))
            if ns is None:
                c["unpriced"] += 1
            else:
                c["priced"] += 1
                c["read_worker_ns"] += ns
    return by_phase


def prices(groups, events, physical, joint, fixed, work):
    clocks = base["decode_prices"](groups, events, physical)
    crossed = base["cross"](
        work["prefill"]["total_disk"],
        {k: v["decode_witness_ns"] for k, v in clocks.items()},
        joint,
        fixed,
    )
    for key, marks in physical.items():
        chains = []
        unknown = 0
        cpu_read_worker_ns = 0
        for gr, (disk, _), (seen, _) in zip(groups, events, marks, strict=True):
            if gr["site"][2] >= 25:
                continue
            n = sum(k not in seen for k in disk)
            unknown += n
            cpu_read_worker_ns += sum(seen[k] for k in disk if k in seen)
            if n:
                chains.append(max((seen[k] for k in disk if k in seen), default=0))
        row = clocks[key]
        check(unknown == row["cpu_read_unpriced"], "new CPU READ count")
        row["cpu_read_worker_ns"] = cpu_read_worker_ns
        row["unpriced_callback_count"] = len(chains)
        row["unpriced_payload_bytes"] = unknown * base["PAY"]
        row["six_unknown_budget"] = unknown_budget(chains, row["decode_witness_ns"], 47 * NS // 6)
    return clocks, crossed


def run(archive):
    # Complete T1-only initialization before base.inputs opens or reconstructs any T2 record.
    p, b, ages, current, entry = start_clock(archive)
    groups, primary, bank, terminal, physical, cut, joint, fixed, origin = base["inputs"](archive)
    check(p == primary and b == bank and len(terminal) == 1000, "independent T1 state")
    control = pinned(PRE / "evidence/receipt.json", ORACLE)
    baseline = fixed["work"]["decode"]["disk_jobs"]
    check(
        baseline == 797
        and control["arms"]["U_aligned"]["continuous"]["decode"]["total_disk"] == 414,
        "oracle/control identity",
    )
    out = {}
    pf_prices = prefill_prices(archive, joint)
    pf = sum(g["phase"] != "decode" for g in groups)
    for name, ref_name in (("P40", "P40"), ("P1000", "P1000"), ("U1262", "U_aligned")):
        events, states = simulate(groups, primary, bank, ages, current, name)
        work = base["summarize"](groups, events)
        clocks, combos = prices(groups[pf:], events[pf:], physical, joint, fixed, work)
        total = work["prefill"]["total_disk"] + work["decode"]["total_disk"]
        sim = control["arms"][ref_name]
        check(
            total >= sim["continuous_total_disk"]
            and work["prefill"]["total_disk"] >= sim["prefill_free_exit"]["total_disk"],
            "causal trajectory improves on exact optimum",
        )
        out[name] = dict(
            phase_work=work,
            states=states,
            prefill_same_site={
                k: prefill_coverage(groups[:pf], events[:pf], prices)
                for k, prices in pf_prices.items()
            },
            decode_prices=clocks,
            conditional=combos,
            total_disk=total,
            excess_over_whole_T2_oracle=total - sim["continuous_total_disk"],
        )
    alt = out["U1262"]
    n = alt["phase_work"]["decode"]["total_disk"]
    reduced = n < min(baseline, out["P40"]["phase_work"]["decode"]["total_disk"])
    room = all(r["six_unknown_budget"]["wall_margin_ns"] > 0 for r in alt["decode_prices"].values())
    return dict(
        status="REPRODUCED_CAUSAL_GLOBAL_CPU_LRU",
        entry=entry,
        arms=out,
        oracle_sha256=ORACLE,
        origin=base["SEALS"],
        t1_costs=origin["t1_prefix"],
        decision_decode="GO_DECODE_FIXTURE_ONLY" if reduced and room else "NO_GO_DECODE_GATE",
        whole_request={
            label: all(r[label]["margin_ns"] >= 0 for r in alt["conditional"].values())
            for label in ("serial", "pipeline", "zero")
        },
        model_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        signal.alarm(120)
        resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        git = ["git", "-C", str(HERE), "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
        check(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        result = run(a.archive)
        result.update(
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            program_sha256=sha(Path(__file__)),
            protocol_sha256=sha(HERE / "protocol.md"),
            prefill_price_protocol_sha256=sha(HERE / "prefill-price.md"),
        )
    except Exception as e:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
