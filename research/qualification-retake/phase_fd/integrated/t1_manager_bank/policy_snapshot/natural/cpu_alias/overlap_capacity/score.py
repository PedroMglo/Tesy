"""Count immutable CPU weight aliases from the sealed T1 victim prefix and T2 reservations."""

import argparse
import hashlib
import json
import os
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
NAT = HERE.parents[1]
replay = run_path(NAT / "replay/screen.py")
need = replay["require"]
FAMILY = "cb70c934dbbe0f1ca7452904718589b44fa906179208e7f95b0c934808d70a42"
PAIR = "bb6e2b508bf35af6001ccbb5bec655ae3235bf69d1a8d74af84b4382b640b889"
REPLAY = "494bb5d2e73b4e129b020118e1bcf2110f253b1c2b565b5d110023129516aa54"
PREFILL = "f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f"
DECODE = "aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a"
K, WINDOW, PAYLOAD = 353, 13221888, 13219200
FIXED, STOP = 4720263168, 20937965568
PADDING = 1000 * (WINDOW - PAYLOAD)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, expected):
    need(digest(path) == expected, "source seal " + path.name)
    return json.loads(path.read_bytes())


def cost(n, aliases):
    need(0 <= aliases <= n, "charged aliases")
    return (
        (n - aliases + 4) * WINDOW
        + ((4096 + 36 * 128 * 4 + 64 * (n + 4) + 4095) // 4096) * 4096
        + PADDING
    )


def intersection_keys(bank, ready):
    return {k for k in bank if k[0] < 25 and k in ready}


class Retained:
    def __init__(self):
        self.order = OrderedDict()
        self.mandatory_shortfall = 0

    def offer(self, key):
        self.order[key] = None
        self.order.move_to_end(key)

    def trim(self, ready, minimum):
        shared = len(intersection_keys(self.order, ready))
        while len(self.order) > minimum and cost(len(self.order), shared) > FIXED:
            removed, _ = self.order.popitem(last=False)
            shared -= removed[0] < 25 and removed in ready
        self.mandatory_shortfall = max(
            self.mandatory_shortfall, cost(len(self.order), shared) - FIXED
        )


def transition(row, ready, on_reserve, after):
    if row.kind == 11:
        if row.a >= 0:
            old = (row.layer, row.a)
            need(old in ready, "reserve did not evict a READY key")
            ready.remove(old)
            on_reserve(old)
        after()
    elif row.kind == 17:
        key = (row.layer, row.expert)
        need(key not in ready, "duplicate publication")
        ready.add(key)
        after()


def before_post(prefix, bank, initial):
    ready = {(r.layer, r.expert) for r in prefix if r.kind == 5 and r.a == 2}
    store = Retained()
    offered = set()

    def offer(key):
        offered.add(key)
        store.offer(key)

    for row in prefix:
        transition(row, ready, offer, lambda: store.trim(ready, K))
    need(list(store.order)[-K:] == bank and ready == initial, "T1 history cut")
    return store, offered


class Extrema:
    def __init__(self, counts):
        self.minimum = counts.copy()
        self.maximum = counts.copy()
        self.total_min = [sum(counts[:25]), sum(counts[25:])]
        self.total_max = self.total_min.copy()

    def observe(self, counts):
        self.minimum = list(map(min, self.minimum, counts))
        self.maximum = list(map(max, self.maximum, counts))
        totals = [sum(counts[:25]), sum(counts[25:])]
        self.total_min = list(map(min, self.total_min, totals))
        self.total_max = list(map(max, self.total_max, totals))


def layer_counts(primary, bank):
    hits = Counter(k[0] for k in bank if k in primary)
    return [hits[i] for i in range(36)]


def phase(call, start):
    return "call5" if call == start else "call148" if call == start + 1 else "decode"


def oracle(disk, eligible, primary, bank, budget):
    # Grant all potentially helpful CPU keys already present in the primary for
    # no data cost even after they leave, and ignore their descriptor cost.
    # For paid keys retain descriptor costs and allow optimal hindsight ordering.
    shared = len(intersection_keys(bank, primary))
    paid = 0
    while cost(K + paid + 1, shared) <= budget:
        paid += 1
    free = intersection_keys(eligible, primary)
    out = {}
    for name, counts in disk.items():
        ranked = sorted((counts[k] for k in eligible - free if counts[k]), reverse=True)
        out[name] = dict(
            free_jobs=sum(counts[k] for k in free),
            paid_jobs=sum(ranked[:paid]),
            paid_key_limit=paid,
            useful_free_keys=sum(k in counts for k in free),
        )
    return out


def score(a):
    pair = load(NAT / "evidence/pair.json", PAIR)
    baseline = load(NAT / "replay/evidence/receipt.json", REPLAY)
    check = replay["execute"](SimpleNamespace(family=a.family, family_sha256=FAMILY))
    need(
        json.loads(json.dumps(check))
        == {
            k: v for k, v in baseline.items() if k not in ("measurement_commit", "protocol_sha256")
        },
        "full observed R0 and carry trajectory",
    )
    raw = a.family / "ON/raw/events.pfj"
    need(digest(raw) == baseline["pfj_sha256"], "PFJ1")
    pfj, _ = replay["fd"].read_journal(raw)
    n = json.loads((a.family / "ON/before-t2.json").read_bytes())["records"]
    prefix = pfj[:n]
    slots, fifo, victims = replay["audit"]["state_before"](prefix)
    need(not fifo and all(s[2] == 2 and not s[3] for s in slots), "full drained initial slots")
    bank_list = list(dict.fromkeys(reversed(victims)))[:K][::-1]
    bank = set(bank_list)
    need(len(bank) == K, "victim suffix")
    init = {(i // 40, v[0]) for i, v in enumerate(slots)}
    store, offered = before_post(prefix, bank_list, init)
    pre_debt = store.mandatory_shortfall
    entry_extra = set(store.order) - bank
    need(len(init) == 1440, "initial primary")
    resources = pair["arms"]["ON"]["physical_maxima"]
    peak = resources["cgroup_peak_bytes"]
    groups = load(a.prefill, PREFILL)["groups"] + load(a.decode, DECODE)["groups"]
    start = groups[0]["call"]
    primary = init.copy()
    state = [(s[0], s[1]) for s in slots]
    cuts = {"entry": layer_counts(primary, bank)}
    extrema = {}
    observed = {}
    ready = init.copy()
    for row in pfj[n:]:
        label = phase(row.call, start)
        if label not in observed:
            observed[label] = Extrema(layer_counts(ready, bank))

        def record(label=label):
            observed[label].observe(layer_counts(ready, bank))

        transition(row, ready, lambda _: None, record)
    saved = defaultdict(Counter)
    disk = defaultdict(Counter)
    first_disk = {}
    first_saved = {}
    info = []
    for gi, g in enumerate(groups):
        call, tile, layer, wave = (g[f] for f in ("call", "tile", "layer", "wave"))
        tier = "cpu" if layer < 25 else "cuda"
        ph = phase(call, start)
        if ph not in extrema:
            extrema[ph] = Extrema(layer_counts(primary, bank))
        for j in g["jobs"]:
            idx = layer * 40 + j["slot"]
            old, old_gen = state[idx]
            key = (layer, j["expert"])
            victim = (layer, old)
            need(
                j["generation"] == old_gen + 1
                and j.get("victim", old) == old
                and victim in primary
                and key not in primary
                and (j["source"] == "bank") == (key in bank),
                "slot/weight source",
            )
            if j["source"] == "disk":
                site = (call, tile, layer, wave, j["ordinal"])
                disk[ph][key] += 1
                disk["all"][key] += 1
                first_disk.setdefault(key, site)
                if key in store.order:
                    need(key in entry_extra, "retroactive extra")
                    saved[ph][key] += 1
                    first_saved.setdefault(key, site)
                    info.append((key, site, tier))
            primary.remove(victim)
            primary.add(key)
            state[idx] = (key[1], old_gen + 1)
            store.trim(primary, K)
            need(set(store.order) >= bank, "lost mandatory bank")
            extrema[ph].observe(layer_counts(primary, bank))
        nxt = groups[gi + 1] if gi + 1 < len(groups) else None
        if not nxt or (call, tile) != (nxt["call"], nxt["tile"]):
            cuts[f"{call}/{tile}"] = layer_counts(primary, bank)
    need(
        [sum(disk[k].values()) for k in ("call5", "call148", "decode")] == [34, 1024, 797],
        "phase totals",
    )
    counts = {}
    for ph in ("call5", "call148", "decode"):
        ids = set(saved[ph])
        counts[ph] = dict(
            jobs=sum(saved[ph].values()),
            unique_keys=len(ids),
            cpu_jobs=sum(v for k, v in saved[ph].items() if k[0] < 25),
            first_ever_paid_keys=sum(
                first_saved[k] == first_disk[k] and phase(first_disk[k][0], start) == ph
                for k in ids
            ),
        )
    need(
        all(first_saved[k] == first_disk[k] for k in first_saved),
        "hit after unsupplied first fault",
    )
    key_hash = hashlib.sha256(json.dumps(sorted(entry_extra)).encode()).hexdigest()
    first_positions = Counter(f"{s[0]}/{s[1]}" for s in first_saved.values())
    paid_keys = offered - bank
    return dict(
        status="TRACE_DERIVED_CPU_ALIAS_CAPACITY",
        plan_sha256=[PREFILL, DECODE],
        family_sha256=FAMILY,
        journal_sha256=baseline["pfj_sha256"],
        protocol_sha256=digest(HERE / "protocol.md"),
        program_sha256=digest(Path(__file__)),
        order="layers 0..24 CPU, 25..35 CUDA; min and max by tier are simultaneous",
        cuts=cuts,
        carry_phase_extrema={k: vars(v) for k, v in extrema.items()},
        observed_r0_ready_extrema={k: vars(v) for k, v in observed.items()},
        resources=dict(
            r0_on=resources,
            r0_off=pair["arms"]["OFF"]["physical_maxima"],
            stop_bytes=STOP,
            cap_bytes=20 << 30,
            bank_standalone_fixed_bytes=FIXED,
            raw_index_bytes=49152,
            primary_cpu_padding_bytes=PADDING,
            incumbent_staging_bytes=4 * WINDOW,
            incremental_four_handoff_pagesets_bytes=4 * WINDOW,
            primary_cpu_payload_bytes=1000 * PAYLOAD,
            primary_gpu_payload_bytes=440 * PAYLOAD,
            measured_vram_including_runtime_bytes=resources["gpu_used_mib"] * 2**20,
        ),
        causal=dict(
            t1_victim_offers=len(victims),
            t1_distinct=len(offered),
            t1_mandatory_shortfall_bytes=pre_debt,
            t2_max_gross_mandatory_shortfall_bytes=store.mandatory_shortfall,
            entry_extra_count=len(entry_extra),
            entry_extra_sha256=key_hash,
            last_extra_count=len(store.order) - K,
            extra_cpu_initial_aliases=len(intersection_keys(entry_extra, init)),
            saved=counts,
            first_saved_site_boundaries=first_positions,
            first_saved_site=min(first_saved.values()) if first_saved else None,
            last_newly_saved_site=max(first_saved.values()) if first_saved else None,
            distinct_saved_keys=len(first_saved),
            saved_allocations=len(info),
        ),
        oracle_valid_for_fixed_tags=dict(
            same_nominal_bank_budget=oracle(disk, paid_keys, init, bank, FIXED),
            fixed_r0_peak_and_stop=oracle(disk, paid_keys, init, bank, STOP - 1 - peak),
        ),
        model_forwards=0,
        weight_bytes_read=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("family", "prefill", "decode", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        row = score(a)
    except Exception as exc:
        (a.new_output_dir / "failure.json").write_text(
            json.dumps(dict(status="FAIL_PRESERVED", reason=repr(exc)))
        )
        raise
    (a.new_output_dir / "receipt.json").write_text(json.dumps(row, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
