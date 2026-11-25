"""Replay a cold secondary RAM cache on the conserved natural C269 T2 journal."""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter, OrderedDict, defaultdict
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROTOCOL = "93b4f8e39bb05774136e4379e679494bad4eb5b736c1545303f9f65d26a1882e"
BASELINE = {
    "nvme_r0_gate/qualified_profile/evidence/receipt.json": (
        "aa62ae8d848bfef8b9f90a6fb97ae455d15273293c752d2ec2da8708521555a0",
        15859171328,
    ),
    "nvme_conversation/postupdate/physical-r01/evidence.json": (
        "42614a3e1c6f4fc137b87f06c002faa0be74ff3f8d32c69840292d75b9585be4",
        16191946752,
    ),
}
SLAB = 4406400
TRIPLE = SLAB * 3
PAGE = 4096
STOP = 20937965568
JOURNAL = 64 + 262144 * 96


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def pinned(path, digest):
    if not path.exists():
        raise FileNotFoundError(path.name)
    need(path.is_file() and not path.is_symlink() and sha(path) == digest, "digest " + path.name)
    return json.loads(path.read_bytes())


def page(n):
    return (n + PAGE - 1) // PAGE * PAGE


def additional(k):
    return (k + 4) * page(TRIPLE) + page(4096 + 36 * 128 * 4 + 64 * (k + 4)) if k else 0


def scope(call, layer):
    return ("prefill" if call <= 2 else "decode") + ("_cpu" if layer < 25 else "_cuda")


class Cache:
    """A hit pins its entry through publication. A miss owns one assembly buffer."""

    def __init__(self, k):
        self.k = k
        self.entries = OrderedDict()
        self.pins = set()
        self.filling = {}
        self.source = {}
        self.prices = defaultdict(Counter)
        self.admissions = {}
        self.busy = 0
        self.peak = 0

    def lookup(self, gen, table_key, segment):
        active, entries = self.filling, self.entries
        need(
            gen not in active and table_key not in {x[0] for x in active.values()},
            "concurrent same key",
        )
        hit = table_key in entries
        self.prices[segment]["lookups"] += 1
        self.prices[segment]["primary_copy_bytes"] += TRIPLE
        if hit:
            root = entries[table_key]
            self.pins.add(table_key)
            entries.move_to_end(table_key)
            self.admissions[root][1] = True
            self.prices[segment]["hits"] += 1
            self.prices[segment]["lookup_copy_bytes"] += TRIPLE
        else:
            root = gen
            self.prices[segment]["misses"] += 1
            if self.k:
                self.prices[segment]["assembly_copy_bytes"] += TRIPLE
                self.busy += 1
                self.peak = max(self.peak, self.busy)
                need(self.busy <= 4, "four assembly buffers")
        active[gen] = (table_key, hit, segment)
        self.source[gen] = root

    def publish(self, gen):
        key, hit, segment = self.filling.pop(gen)
        if hit:
            self.pins.remove(key)
        elif self.k:
            self.busy -= 1
            if len(self.entries) == self.k:
                victim = next((k for k in self.entries if k not in self.pins), None)
                if victim is None:
                    self.prices[segment]["bypassed"] += 1
                    return
                del self.entries[victim]
            self.entries[key] = gen
            self.admissions[gen] = [segment, False]
            self.prices[segment]["installed"] += 1

    def finish(self, required, returned, by_prefill_return):
        need(not self.filling and not self.pins and not self.busy, "drained replay")
        for segment, used in self.admissions.values():
            self.prices[segment]["unused_installs"] += int(not used)
        roots = {self.source[g] for g in required if g in self.source}
        prefill_bytes = 0
        for gen, source in self.source.items():
            call, count = returned[gen]
            segment = self.prices[scope(call, gen[0])]
            segment["baseline_returned_bytes"] += count
            if source != gen:
                segment["returned_bytes_avoided"] += count
            else:
                segment["remaining_returned_bytes"] += count
                prefill_bytes += by_prefill_return.get(gen, 0)
        data = dict(self.prices)
        mm = sum(v["lookups"] for s, v in data.items() if s.startswith("decode"))
        hits = sum(v["hits"] for s, v in data.items() if s.startswith("decode"))
        need(mm > 0, "decode work")
        return dict(
            capacity=self.k,
            additional_bytes=additional(self.k),
            peak_assembly_buffers=self.peak,
            prices=data,
            decode_lookups=mm,
            decode_hits=hits,
            decode_meets_20_percent=hits * 5 >= mm,
            remaining_origin_bytes_by_prefill_return=prefill_bytes,
            required_prefill_miss_generations=len(roots),
            required_prefill_payload_bytes=len(roots) * TRIPLE,
            required_prefill_original_read_returns=sum(returned[g][1] for g in roots),
        )


def replay(events, identity):
    caches = [Cache(k) for k in (0, 239, 353, 36 * 128)]
    claimed = {}
    required = set()
    inherited = set()
    resident = set()
    fd_return = defaultdict(int)
    prefill_fd_return = defaultdict(int)
    prefill_closed = False
    for e in events:
        gen = identity(e)
        key = (e.layer, e.expert)
        if e.kind == 2 and e.call == 2:
            prefill_closed = True
        elif e.kind == 5:
            if e.a == 1:
                inherited.add(key)
            if e.a == 2:
                resident.add(key)
        elif e.kind == 8:
            need(e.b == SLAB, "authenticated expert component size")
        elif e.kind == 10 and e.call in (1, 2):
            required.add(gen)
        elif e.kind == 13 and e.call > 0:
            need(gen not in claimed, "unique claim")
            claimed[gen] = e.call
            for c in caches:
                c.lookup(gen, key, scope(e.call, e.layer))
        elif e.kind == 15 and e.call > 0:
            fd_return[gen] += e.c
            if not prefill_closed and e.call in (1, 2):
                prefill_fd_return[gen] += e.c
        elif e.kind == 17 and gen in claimed:
            for c in caches:
                c.publish(gen)
    returned = {gen: (call, fd_return[gen]) for gen, call in claimed.items()}
    need(all(n >= TRIPLE for _, n in returned.values()), "complete returned bytes")
    # Exclude all inherited in-flight identities, including a later re-load of one.
    keys = {(g[0], g[3]) for g in required if claimed.get(g) in (1, 2)} - inherited
    floors = {
        s: sum(1 for layer, _ in keys if (layer < 25) == (s == "cpu")) for s in ("cpu", "cuda")
    }
    return dict(
        required_distinct=len(keys),
        required_by_tier=floors,
        initial_resident_reloads=len(keys & resident),
        inherited_keys_granted_free=len(inherited),
        cold_fixed_primary_floor_bytes=len(keys) * TRIPLE,
        capacities=[c.finish(required, returned, prefill_fd_return) for c in caches[:3]],
        unlimited_cold_diagnostic=caches[-1].finish(required, returned, prefill_fd_return),
    )


def budget(row, count):
    ns = Decimal(10**9)

    def rounded(key, rounding):
        return int((Decimal(str(row[key])) * ns).to_integral_value(rounding=rounding))

    need(row["predicted_n"] == 47 and count in (46, 47), "denominator")
    allowed_ns = 10**10 + rounded("prefill_s", ROUND_CEILING) + rounded("decode_s", ROUND_CEILING)
    allowed_ns -= rounded("first_final_s", ROUND_FLOOR) + count * 10**9 // 6
    return allowed_ns, max(0, (allowed_ns * 9 + 1) // 2)


def evaluate(on_root, on_hash, off_root, off_hash):
    need(sha(HERE / "protocol.md") == PROTOCOL, "protocol freeze")
    peaks = []
    for name, (digest, peak) in BASELINE.items():
        need(pinned(ROOT / name, digest)["maxima"]["cgroup_peak_bytes"] == peak, "historical peak")
        peaks.append(peak)
    for budget, k in ((3 * 2**30, 239), (STOP - max(peaks) - JOURNAL, 353)):
        need(additional(k) <= budget < additional(k + 1), "capacity calibration")
    on = pinned(on_root / "receipt.json", on_hash)
    off = pinned(off_root / "receipt.json", off_hash)
    need(
        on["status"] == "PASS_C281_PFJ_ON"
        and off["status"] == "PASS_C281_PFJ_OFF"
        and on["gates"] == off["gates"]
        and on["trajectories"] == off["trajectories"],
        "contemporary pair",
    )
    sealed = pinned(on_root / "journal-audit.json", on["journal_audit_sha256"])
    need(sealed["status"] == "PASS" and sealed["fd_identity_checked"], "FD identity")
    source = HERE.parent / "analyse.py"
    spec = importlib.util.spec_from_file_location("phasefd_l2_audit", source)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    events, head = audit.read_journal(on_root / "raw/events.pfj")
    need(head["journal_sha256"] == on["journal_sha256"], "journal identity")
    fresh = audit.audit(events, head)
    # Use the original authenticated inode/FD check; reopening the model is unnecessary.
    need(dict(fresh, fd_identity_checked=True) == sealed, "conservation replay")
    need([c["tokens"] for c in sealed["calls"]] == [5, 148] + [1] * 46, "nominal calls")
    result = replay(events, audit.identity)
    phase = sealed["nominal_prefill"]
    need(
        result["required_distinct"]
        == phase["compulsory_unique"] + result["initial_resident_reloads"],
        "increment relative to ideal primary proof",
    )
    k0 = result["capacities"][0]
    need(
        sum(
            p["baseline_returned_bytes"] for s, p in k0["prices"].items() if s.startswith("prefill")
        )
        == phase["origin_returned_bytes"]
        and k0["remaining_origin_bytes_by_prefill_return"]
        == phase["origin_returned_bytes"] - phase["returned_after_prefill_for_origin_bytes"],
        "cut/completion conservation",
    )
    caps = on["own_ON_price"]
    off_peak = off["maxima"]["cgroup_peak_bytes"]
    on_peak = on["maxima"]["cgroup_peak_bytes"]
    headroom = STOP - max(off_peak + JOURNAL, on_peak)
    for c in result["capacities"]:
        c["fits_observed_envelope"] = c["additional_bytes"] < headroom
    conclusions = {}
    for count, price in (
        (47, "C281_M4_predicted_tokens"),
        (46, "optimistic_AR_post_first_evaluations"),
    ):
        ns, target = budget(on["rows"][1], count)
        need(
            caps[price]["conditional_prompt_budget_ns_upper"] == ns
            and caps[price]["scenario_bytes_at_4_5GBps"] == target
            and caps[price]["denominator"] == count,
            "own ON clocks",
        )
        d = []
        for c in result["capacities"]:
            necessary_fits = c["required_prefill_payload_bytes"] <= target
            fits = c["remaining_origin_bytes_by_prefill_return"] <= target
            eligible = bool(
                c["capacity"]
                and necessary_fits
                and fits
                and c["decode_meets_20_percent"]
                and c["fits_observed_envelope"]
            )
            d.append(
                dict(
                    k=c["capacity"],
                    necessary_prefill_volume_fits=necessary_fits,
                    observed_completion_volume_fits=fits,
                    triage_eligible=eligible,
                )
            )
        shortfall = max(0, result["cold_fixed_primary_floor_bytes"] - target)
        minimum_warm_keys = (shortfall + TRIPLE - 1) // TRIPLE
        conclusions[price] = dict(
            allowed_ns=ns,
            allowed_bytes=target,
            shortfall_bytes=shortfall,
            minimum_warm_keys_for_compulsory_floor=minimum_warm_keys,
            minimum_warm_payload_bytes=minimum_warm_keys * TRIPLE,
            capacity_screen=d,
        )
    screens = list(conclusions.values())
    if all(s["shortfall_bytes"] > 0 for s in screens):
        verdict = "NO_GO_COLD_HOST_CACHE_FIXED_PRIMARY_VOLUME"
    elif any(s["shortfall_bytes"] for s in screens):
        verdict = "DENOMINATOR_DEPENDENT"
    elif any(c["triage_eligible"] for c in screens[0]["capacity_screen"]):
        verdict = "GO_COPY_FIXTURE_ONLY"
    else:
        verdict = "NO_GO_LRU_SCREEN"
    return dict(
        status="PASS",
        decision=verdict,
        protocol_sha256=PROTOCOL,
        on_sha256=on_hash,
        off_sha256=off_hash,
        journal_sha256=head["journal_sha256"],
        audit_program_sha256=sha(source),
        audit_sha256=on["journal_audit_sha256"],
        observed_memory_margin_bytes=headroom,
        off_peak=off_peak,
        on_peak=on_peak,
        clock_transfer=on["clock_transfer"],
        gates=conclusions,
        **result,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("on", "off", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("on-sha256", "off-sha256"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = evaluate(a.on, a.on_sha256, a.off, a.off_sha256)
        rc = 0
    except FileNotFoundError as exc:
        result = dict(status="NOT_RUN_RAW_REQUIRED", missing=exc.filename or str(exc))
        rc = 1
    except (OSError, KeyError, TypeError, ValueError) as exc:
        result = dict(status="FAIL_PRESERVED", error=str(exc))
        rc = 1
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
