"""Replay victim-only secondary storage starting empty at the measured T2 boundary."""

import argparse
import importlib.util
import json
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


fd = module(INT / "analyse.py", "pfj_victim_audit")
host = module(INT / "host_cache/screen.py", "pfj_host_cost")
need, T = host.need, host.TRIPLE
PLAN = "c5b9cac1354ff9d58563d1a8167a39abeb74ac376d5741cedb8de203d62f862b"
HOST = "a3398265b4bf33ed75f4898b346c2d9a988865cd5ca9cf98668826b52d41f700"
PROTOCOL = "040196bb0474f4218c5346ce231bf3d3abc4d62f38f1a44a63548c044c6a3abd"


class Victims:
    def __init__(self, k):
        self.k = k
        self.resident = OrderedDict()
        self.pins = Counter()
        self.origins = {}
        self.mandatory_hits = 0
        self.stats = defaultdict(Counter)
        self.misses_by_cut = 0

    def reserve(self, generation, victim, segment, mandatory=False):
        k = (generation[0], generation[3])
        row = self.stats[segment]
        hit = k in self.resident
        need(generation not in self.origins, "duplicate reservation")
        self.origins[generation] = (hit, segment)
        if hit:
            self.pins[k] += 1
            insert_phase, used = self.resident[k]
            if not used:
                self.stats[insert_phase]["reused_installs"] += 1
                self.resident[k] = (insert_phase, True)  # Keep the same LRU position.

            self.mandatory_hits += int(mandatory)
        if victim is None or self.k == 0:
            return
        row["victim_offers"] += 1
        if victim in self.resident:
            self.resident.move_to_end(victim)
            row["existing_payload_refreshes"] += 1
            return
        if len(self.resident) == self.k:
            old = next((key for key in self.resident if not self.pins[key]), None)
            if old is None:
                row["pinned_bypasses"] += 1
                return
            del self.resident[old]
        self.resident[victim] = (segment, False)
        row["copies_of_victims"] += 1
        row["victim_to_ram_bytes"] += T

    def dispatch(self, generation):
        hit, segment = self.origins[generation]
        s = self.stats[segment]
        s["hits" if hit else "misses"] += 1
        s["primary_set_bytes"] += T
        if hit:
            s["ram_to_staging_bytes"] += T

    def read(self, generation, n, by_cut):
        hit, segment = self.origins[generation]
        self.stats[segment]["avoided_fd_returns" if hit else "remaining_fd_returns"] += n
        if by_cut and not hit:
            self.misses_by_cut += n

    def publish(self, generation):
        hit, _ = self.origins.pop(generation)
        if hit:
            key = (generation[0], generation[3])
            self.pins[key] -= 1
            if self.pins[key] == 0:
                del self.pins[key]

    def report(self):
        need(not self.pins and not self.origins, "unfinished generation/pins")
        n = sum(v["hits"] + v["misses"] for k, v in self.stats.items() if k.startswith("decode"))
        h = sum(v["hits"] for k, v in self.stats.items() if k.startswith("decode"))
        eligible = sum(v["copies_of_victims"] for v in self.stats.values())
        for s in self.stats.values():
            s["unused_installs"] = s["copies_of_victims"] - s["reused_installs"]
        return dict(
            capacity=self.k,
            additional_bytes=host.additional(self.k),
            by_phase_tier=dict(self.stats),
            decode_hits=h,
            decode_claims=n,
            decode_meets_20_percent=h * 5 >= n,
            victim_installs=eligible,
            mandatory_hits=self.mandatory_hits,
            prefill_origin_bytes_by_return=self.misses_by_cut,
        )


def replay(rows, mandatory, capacities):
    caches = [Victims(k) for k in capacities]
    slots = {}
    initial = set()
    ever = set()
    needs = set()
    served = set()
    reserved = set()
    actually_mandatory = set()
    before_return = True
    for r in rows:
        gen = fd.identity(r)
        slot = r.layer, r.slot
        key = r.layer, r.expert
        if r.kind == 5:
            slots[slot] = (r.expert, r.gen, r.a)
            if r.a:
                initial.add(key)
                ever.add(key)
        elif r.kind == 2 and r.call == 2:
            before_return = False
        elif r.kind == 10 and r.call in (1, 2):
            needs.add(key)
        elif r.kind == 11:
            old, g, state = slots[slot]
            need(
                state in (0, 2) and old == r.a and g + 1 == r.gen and gen not in reserved,
                "victim state or generation",
            )
            selected = gen in mandatory
            if selected:
                need(
                    mandatory[gen] == (r.call, r.tile, r.layer, r.wave) and key not in ever,
                    "mandatory key already available or wrong wave",
                )
                actually_mandatory.add(gen)
            for c in caches:
                c.reserve(
                    gen,
                    (r.layer, old) if state == 2 else None,
                    host.scope(r.call, r.layer),
                    selected,
                )
            ever.add(key)
            slots[slot] = (r.expert, r.gen, 1)
            reserved.add(gen)
        elif r.kind == 13 and r.call > 0:
            need(gen in reserved and gen not in served, "duplicate dispatch")
            for c in caches:
                c.dispatch(gen)
            served.add(gen)
        elif r.kind == 15 and r.call > 0:
            need(gen in served, "pread without dispatch")
            for c in caches:
                c.read(gen, r.c, before_return and r.call in (1, 2))
        elif r.kind == 17:
            need(slots[slot] == (r.expert, r.gen, 1), "unexpected publishing generation")
            if r.call > 0:
                for c in caches:
                    c.publish(gen)
            slots[slot] = (r.expert, r.gen, 2)
    need(
        actually_mandatory == set(mandatory) and served == reserved,
        "mandatory/reserve conservation",
    )
    return len(needs - initial), [c.report() for c in caches]


def evaluate(plan_root, on_root, off_root):
    need(host.sha(HERE / "protocol.md") == PROTOCOL, "freeze")
    base = host.pinned(INT / "host_cache/evidence/receipt.json", HOST)
    p = host.pinned(plan_root / "receipt.json", PLAN)
    plan = host.pinned(plan_root / "plan.json", p["plan_sha256"])
    on = host.pinned(on_root / "receipt.json", base["on_sha256"])
    off = host.pinned(off_root / "receipt.json", base["off_sha256"])
    sealed = host.pinned(on_root / "journal-audit.json", base["audit_sha256"])
    rows, head = fd.read_journal(on_root / "raw/events.pfj")
    need(
        on["status"] == "PASS_C281_PFJ_ON"
        and off["status"] == "PASS_C281_PFJ_OFF"
        and on["trajectories"] == off["trajectories"]
        and head["journal_sha256"] == base["journal_sha256"] == plan["journal_sha256"]
        and fd.audit(rows, head) == dict(sealed, fd_identity_checked=False)
        and sealed["fd_identity_checked"],
        "sealed journal",
    )
    m = {}
    for group in plan["groups"]:
        site = tuple(group["site"])
        for j in group["experts"]:
            gen = (site[2], j["slot"], j["generation"], j["expert"])
            need(gen not in m, "duplicate plan generation")
            m[gen] = site
    need(len(m) == 875, "plan shape")
    unique, reports = replay(rows, m, (0, 239, 353, 4608))
    need(
        unique == sealed["nominal_prefill"]["compulsory_unique"], "distinct warm primary exemption"
    )
    old = base["capacities"][0]
    for name, s in reports[0]["by_phase_tier"].items():
        orig = old["prices"][name]
        need(
            s["misses"] == orig["lookups"]
            and s["remaining_fd_returns"] == orig["baseline_returned_bytes"],
            "K0 control",
        )
    fixed = plan["fixed_outside_callbacks_ns"]
    service = plan["original_service_floor_ns"]
    times = {str(n) + "/" + str(d): fixed + service * n // d for n, d in ((1, 1), (4, 5))}
    need(
        min(times.values()) > 10**10 and all(r["mandatory_hits"] == 0 for r in reports),
        "unremoved temporal floor",
    )
    for r in reports:
        r["fits_memory"] = r["additional_bytes"] < base["observed_memory_margin_bytes"]
        r["meets_volume"] = {
            k: r["prefill_origin_bytes_by_return"] <= v["allowed_bytes"]
            for k, v in base["gates"].items()
        }
    volume = {}
    for k, v in base["gates"].items():
        short = max(0, unique * T - v["allowed_bytes"])
        volume[k] = dict(
            allowed_bytes=v["allowed_bytes"],
            deficit=short,
            extra_warm_keys_at_least=(short + T - 1) // T,
        )
    return dict(
        status="PASS",
        decision="NO_GO_T2_ONLY_VICTIMS_FIXED_DEMAND_SERVICE",
        volume=volume,
        distinct_absent=unique,
        payload_floor=unique * T,
        capacities=reports,
        mandatory_jobs=len(m),
        fixed_ns=fixed,
        service_floor_ns=service,
        joint_time_floor_ns=times,
        sources=dict(
            protocol=PROTOCOL,
            plan=PLAN,
            plan_data=p["plan_sha256"],
            on=base["on_sha256"],
            off=base["off_sha256"],
            journal=base["journal_sha256"],
            audit=base["audit_sha256"],
            host_cache=HOST,
        ),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("plan-dir", "on-dir", "off-dir", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    args = ap.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result = evaluate(args.plan_dir, args.on_dir, args.off_dir)
    except Exception as e:
        result = dict(status="FAIL_PRESERVED", error=f"{type(e).__name__}: {e}")
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    raise SystemExit(result["status"] != "PASS")
