"""Apply the causally sealed T1 victim bank to two separately timed T2 trajectories."""

import argparse
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
PROTO = "2db4b4d1e3dc9989cc3c837d997cfc4ceee33478731ca4382b168e7a2b1bba32"
PRIOR = "78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43"
CONTROL = "1edac104fb4a96482cabd1ad35deb357e49a1823bc8a814f26149affd5aa7aa9"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


v = module(INT / "t2_victims/screen.py", "warm_victims")
host, fd, T, need = v.host, v.fd, v.T, v.need
planner = module(INT / "cold_read_fixture/plan.py", "warm_plan")
oracle = module(INT / "warm_oracle/screen.py", "warm_times")
limits, mandatory = planner.limits, planner.mandatory


def fingerprint(keys):
    return hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest()


def price(groups, hits, fixed):
    raw = sum(mandatory.lower_bound([t for g, t in group if g not in hits]) for group in groups)
    return dict(
        raw_floor_ns=raw,
        first_at_1_ns=fixed + raw,
        first_at_4_5_ns=fixed + 4 * raw // 5,
        hits_in_first_groups=sum(g in hits for group in groups for g, _ in group),
    )


def subgroup_prices(plan, rows):
    timed = oracle.jobs({"groups": plan}, rows)
    result = []
    for group, values in zip(plan, timed, strict=True):
        line = []
        for j, (key, t) in zip(group["experts"], values, strict=True):
            need(key == (group["site"][2], j["expert"]), "READ identity")
            line.append(((key[0], j["slot"], j["generation"], key[1]), t))
        result.append(line)
    return result


class Policy:
    def __init__(self, family, k, keys):
        self.family = family
        self.victims = v.Victims(k) if family == "victims" else None
        self.pub = host.Cache(k) if family == "publication" else None
        self.hits = set()
        self.returned = {}
        self.by_cut = defaultdict(int)
        for key in keys:
            src = "initial_cpu" if key[0] < 25 else "initial_cuda"
            if self.victims is not None:
                self.victims.resident[key] = (src, False)
                self.victims.stats[src]["copies_of_victims"] += 1
            else:
                sentinel = (key[0], -1, -1, key[1])
                self.pub.entries[key] = sentinel
                self.pub.admissions[sentinel] = [src, False]

    def reserve(self, g, victim, seg):
        if self.victims is not None:
            self.victims.reserve(g, victim, seg)
            if self.victims.origins[g][0]:
                self.hits.add(g)

    def dispatch(self, g, call, seg):
        need(g not in self.returned, "duplicate workload")
        self.returned[g] = [call, 0]
        if self.victims is not None:
            self.victims.dispatch(g)
        else:
            self.pub.lookup(g, (g[0], g[3]), seg)
            if self.pub.filling[g][1]:
                self.hits.add(g)

    def read(self, g, count, before):
        self.returned[g][1] += count
        if before:
            self.by_cut[g] += count
        if self.victims is not None:
            self.victims.read(g, count, before)

    def publish(self, g):
        if self.victims is not None:
            self.victims.publish(g)
        else:
            self.pub.publish(g)

    def result(self):
        if self.victims is not None:
            r = self.victims.report()
            stats = r["by_phase_tier"]
        else:
            r = self.pub.finish(set(), self.returned, self.by_cut)
            stats = r["prices"]
        bytes_ = sum(n for g, n in self.by_cut.items() if g not in self.hits)
        by_decode = [g for g, (call, _) in self.returned.items() if call >= 3]
        return dict(
            counts={k: dict(vals) for k, vals in stats.items() if not k.startswith("initial_")},
            remaining_prefill_bytes=bytes_,
            decode_hits=sum(g in self.hits for g in by_decode),
            decode_jobs=len(by_decode),
            prefill_hits=sum(
                key in self.hits and self.returned[key][0] in (1, 2) for key in self.hits
            ),
        )


def simulate(rows, policy):
    slots = {}
    before = True
    for r in rows:
        g = fd.identity(r)
        pos = r.layer, r.slot
        if r.kind == 5:
            slots[pos] = (r.expert, r.gen, r.a)
        elif r.kind == 2 and r.call == 2:
            before = False
        elif r.kind == 11:
            old, gen, st = slots[pos]
            need(st in (0, 2) and old == r.a and gen + 1 == r.gen, "victim lineage")
            policy.reserve(g, (r.layer, old) if st == 2 else None, host.scope(r.call, r.layer))
            slots[pos] = (r.expert, r.gen, 1)
        elif r.kind == 13 and r.call > 0:
            policy.dispatch(g, r.call, host.scope(r.call, r.layer))
        elif r.kind == 15 and r.call > 0:
            policy.read(g, r.c, before and r.call in (1, 2))
        elif r.kind == 17:
            need(slots[pos] == (r.expert, r.gen, 1), "publish lineage")
            if r.call > 0:
                policy.publish(g)
            slots[pos] = (r.expert, r.gen, 2)
    return policy.result()


def eligible_sets(rows):
    initial = {(r.layer, r.expert) for r in rows if r.kind == 5 and r.a}
    inherited = {(r.layer, r.expert) for r in rows if r.kind == 5 and r.a == 1}
    demand = {fd.identity(r) for r in rows if r.kind == 10 and r.call in (1, 2)}
    claimed = {fd.identity(r) for r in rows if r.kind == 13 and r.call in (1, 2)}
    return dict(
        victims={(g[0], g[3]) for g in demand} - initial,
        publication={(g[0], g[3]) for g in demand & claimed} - inherited,
    )


def analyse_arm(rows, observed, raw, meta, data, memory):
    entered = [r for r in rows if r.kind == 1]
    ended = [r for r in rows if r.kind == 2]
    need(
        [r.a for r in entered] == [5, 148] + [1] * 46
        and [r.call for r in ended] == list(range(1, 49)),
        "T2 geometry",
    )
    calls = [dict(start_ns=a.ns, end_ns=b.ns) for a, b in zip(entered, ended, strict=True)]
    clock = limits.joint_clock(rows, calls, raw, observed)
    reference = mandatory.evaluate(rows, raw, observed, clock)
    fixed = reference["fixed_outside_callbacks_ns"]["first"]
    start = int(raw["request_started_monotonic"] * 1e9)
    first = start + int(raw["stream_metrics"]["first_final_content_chunk_s"] * 1e9)
    plan, baseline = planner.assemble(rows, meta, start, first)
    groups = subgroup_prices(plan, rows)
    need(
        baseline
        == reference["mandatory_floor_ns"]["first"]
        == price(groups, set(), fixed)["raw_floor_ns"],
        "control clock",
    )
    volumes = eligible_sets(rows)
    budgets = {str(n): host.budget(observed, n)[1] for n in (47, 46)}
    out = []
    for family, needed in volumes.items():
        for n in (239, 353):
            info = data["capacities"][str(n)]
            for warm in (False, True):
                if warm and not info["identified"]:
                    out.append(
                        dict(family=family, k=n, warm=True, decision="INCONCLUSIVE_INITIAL_CONTENT")
                    )
                    continue
                keys = [tuple(k) for k in info["ordered_keys"]] if warm else []
                s = set(keys)
                need(
                    len(keys) == len(s) and len(keys) == (n if warm else 0),
                    "complete initial content",
                )
                model = Policy(family, n, keys)
                r = simulate(rows, model)
                hits = model.hits
                relaxed = {g for group in groups for g, _ in group if (g[0], g[3]) in s}
                actual = price(groups, hits, fixed)
                ideal = price(groups, relaxed, fixed)
                need(
                    (hits & {g for group in groups for g, _ in group}).issubset(relaxed),
                    "first demand cannot be saved by earlier T2 victim/publication",
                )
                volume = (len(needed) - len(needed & s)) * T
                need(
                    volume <= r["remaining_prefill_bytes"]
                    and ideal["raw_floor_ns"] <= actual["raw_floor_ns"],
                    "optimistic inclusion",
                )
                allowed_ram = host.additional(n) < memory
                hit_gate = 5 * r["decode_hits"] >= r["decode_jobs"]

                def passes(time_ns, volume_, count):
                    return time_ns <= 10**10 and volume_ <= budgets[count]

                decisions = {}
                for scale, tname in (("1", "first_at_1_ns"), ("4/5", "first_at_4_5_ns")):
                    decisions[scale] = {
                        count: dict(
                            ideal_joint=passes(ideal[tname], volume, count),
                            finite_joint=passes(actual[tname], r["remaining_prefill_bytes"], count),
                        )
                        for count in ("47", "46")
                    }
                gates = decisions["1"]["47"]
                verdict = (
                    "NO_GO_SEALED_SELECTION_RELAXED"
                    if not gates["ideal_joint"]
                    else "GO_COPY_FIXTURE_ONLY"
                    if gates["finite_joint"] and hit_gate and allowed_ram
                    else "NO_GO_FINITE_POLICY"
                )
                out.append(
                    dict(
                        family=family,
                        k=n,
                        warm=warm,
                        decision=verdict,
                        pref_compulsory_keys=len(needed),
                        warm_compulsory_keys=len(needed & s),
                        relaxed_payload_bytes=volume,
                        ram_fits=allowed_ram,
                        additional_ram=host.additional(n),
                        decode_gate=hit_gate,
                        relaxed_time=ideal,
                        finite_time=actual,
                        gates=decisions,
                        **r,
                    )
                )
    return dict(
        arms=out,
        budgets=budgets,
        first_jobs=sum(map(len, groups)),
        fixed_ns=fixed,
        original_service_floor_ns=baseline,
        remaining_memory_bytes=memory,
    )


def run(a):
    need(host.sha(HERE / "protocol.md") == PROTO, "freeze")
    capture = host.pinned(a.capture_dir / "receipt.json", a.capture_sha256)
    need(
        capture["status"] == "PASS_T1_VICTIM_WINDOW_AND_T2_REFERENCE"
        and capture["prior_on_sha256"] == PRIOR,
        "new natural capture",
    )
    seal = host.pinned(a.capture_dir / "before-t2.json", capture["before_t2_sha256"])
    selection = host.pinned(
        a.capture_dir / "before-t2-candidates.json", seal["candidate_file_sha256"]
    )
    for n in (239, 353):
        s = selection["capacities"][str(n)]
        need(
            fingerprint(s["ordered_keys"]) == s["ordered_keys_sha256"] and s["capacity"] == n,
            "ordered selection",
        )
    cert = host.pinned(a.capture_dir / "boundary-audit.json", capture["boundary_audit_sha256"])
    struct = cert["structure"]
    need(
        cert["status"] == "PASS" and cert["prefix"] == selection and struct["census_fd_checked"],
        "sealed pre-suffix selection",
    )
    prior = host.pinned(a.prior_on_dir / "receipt.json", PRIOR)
    oldvol = host.pinned(INT / "host_cache/evidence/receipt.json", v.HOST)
    oldvictim = host.pinned(INT / "t2_victims/receipt.json", CONTROL)
    reference_plan = host.pinned(a.plan_dir / "receipt.json", v.PLAN)
    raw_old = host.pinned(a.prior_on_dir / "raw/T2-result.json", reference_plan["t2_result_sha256"])
    need(
        capture["t2_result_sha256"] == a.current_result_sha256
        and capture["t1_candidates_sha256"] == seal["candidate_file_sha256"],
        "physical receipt seals",
    )
    raw_now = host.pinned(a.capture_dir / "raw/T2-result.json", a.current_result_sha256)
    need(capture["trajectories"] == prior["trajectories"], "matched trajectories")
    old, ho = fd.read_journal(a.prior_on_dir / "raw/events.pfj")
    new, hn = fd.read_journal(a.capture_dir / "raw/events.pfj")
    need(
        ho["journal_sha256"] == oldvol["journal_sha256"] == struct["prior_journal_sha256"]
        and hn["journal_sha256"] == capture["journal_sha256"] == struct["journal_sha256"],
        "PFJ identities",
    )
    cap_audit = module(INT / "t1_capture/audit.py", "prefix_state")
    cut = seal["records"]
    shift = selection["t1_calls"]
    need(
        cut == struct["first_t2_record"]
        and cap_audit.record_digest(new[:cut]) == seal["sha256"]
        and cap_audit.capture_prefix(new[:cut]) == selection,
        "prefix-first seal",
    )
    escrow, queue, _ = cap_audit.state_before(new[:cut])
    template = sorted((r for r in old if r.kind == 5), key=lambda r: (r.layer, r.slot))
    need(
        len(escrow) == len(template) == 1440
        and not queue
        and not any(x[2] == 1 or x[3] for x in escrow),
        "T2 drained cut required",
    )
    initial = [
        r._replace(expert=x[0], gen=x[1], a=x[2], b=x[3])
        for r, x in zip(template, escrow, strict=True)
    ]
    need(
        initial == template and new[cut].kind == 1 and new[cut].call == shift + 1, "identical entry"
    )
    tail = initial + [r._replace(call=r.call - shift if r.call > 0 else r.call) for r in new[cut:]]
    meta = planner.metadata(a.inventory)
    current_mem = min(
        oldvol["observed_memory_margin_bytes"], host.STOP - capture["maxima"]["cgroup_peak_bytes"]
    )
    current = analyse_arm(tail, capture["rows"][1], raw_now, meta, selection, current_mem)
    transported = analyse_arm(
        old, prior["rows"][1], raw_old, meta, selection, oldvol["observed_memory_margin_bytes"]
    )
    for r in transported["arms"]:
        if not r["warm"]:
            prior_set = (
                oldvol["capacities"] if r["family"] == "publication" else oldvictim["capacities"]
            )
            ref = next(x for x in prior_set if x["capacity"] == r["k"])
            volkey = (
                "remaining_origin_bytes_by_prefill_return"
                if r["family"] == "publication"
                else "prefill_origin_bytes_by_return"
            )
            need(
                r["decode_hits"] == ref["decode_hits"]
                and r["remaining_prefill_bytes"] == ref[volkey],
                "cold ablation",
            )
    need(
        transported["original_service_floor_ns"] == 6231568365
        and transported["fixed_ns"] == 5996895714,
        "frozen prior clock",
    )
    return dict(
        status="PASS",
        sources=dict(
            protocol=PROTO,
            capture=a.capture_sha256,
            seal=capture["before_t2_sha256"],
            selected=seal["candidate_file_sha256"],
            journal=hn["journal_sha256"],
            prior=PRIOR,
            boundary=capture["boundary_audit_sha256"],
            current_raw=a.current_result_sha256,
            prior_raw=reference_plan["t2_result_sha256"],
            inventory=planner.INVENTORY,
        ),
        same_service_order=struct["service_interleaving_equal"],
        t1_costs={
            n: {k: val for k, val in info.items() if k != "ordered_keys"}
            for n, info in selection["capacities"].items()
        },
        current=current,
        historical_order_projection=transported,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("capture-dir", "prior-on-dir", "plan-dir", "inventory", "new-output-dir"):
        ap.add_argument("--" + k, type=Path, required=True)
    for k in ("capture-sha256", "current-result-sha256"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        out = run(a)
    except Exception as e:
        out = dict(status="FAIL_PRESERVED", error=f"{type(e).__name__}: {e}")
    (a.new_output_dir / "receipt.json").write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")
    raise SystemExit(out["status"] != "PASS")
