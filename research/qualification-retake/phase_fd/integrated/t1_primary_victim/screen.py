"""Test whether eviction cost changes payable reads after a sealed first turn."""

import argparse
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
router = run_path(str(HERE.parent / "t1_router_window/volume.py"))
src = router["src"]
check = src.need
PAYLOAD = router["PAYLOAD"]
ROUTER_RECEIPT = "37f068e20acc7734492aa2d9524e7f0e69ca79f1488582acf7b986bb76a84765"


def charge(counts, layer, expert, bank):
    origin = "ram" if (layer, expert) in bank else "disk"
    counts[origin] += 1
    counts[f"{origin}_{'cpu' if layer < 25 else 'cuda'}"] += 1


class Pool:
    def __init__(self, initial):
        self.slots = list(initial)
        self.age = [0] * len(initial)

    def wave(self, layer, demand, bank, prefer_backed, tick, counts):
        pins = set(demand)
        check(len(pins) == len(demand) <= len(self.slots), "invalid simultaneous wave")
        for expert in demand:
            if expert in self.slots:
                slot = self.slots.index(expert)
                counts["primary"] += 1
            else:
                charge(counts, layer, expert, bank)
                if -1 in self.slots:
                    slot = self.slots.index(-1)
                else:
                    free = [i for i, occupant in enumerate(self.slots) if occupant not in pins]
                    slot = min(
                        free,
                        key=lambda i: (
                            prefer_backed and (layer, self.slots[i]) not in bank,
                            self.age[i],
                            i,
                        ),
                    )
                self.slots[slot] = expert
            self.age[slot] = tick
        check(pins <= set(self.slots), "lost simultaneous consumer")

    def restore(self, layer, wanted, bank, tick, counts):
        previous = {e: age for e, age in zip(self.slots, self.age, strict=True) if e >= 0}
        for expert in wanted:
            if expert >= 0 and expert not in previous:
                charge(counts, layer, expert, bank)
        self.slots = list(wanted)
        self.age = [previous.get(e, tick) for e in wanted]


def inputs(rows):
    cut = next(i for i, r in enumerate(rows) if r.kind == 2 and r.call == 2)
    start_rows = [r for r in rows if r.kind == 5]
    initial = [[-1] * 40 for _ in range(36)]
    for r in start_rows:
        initial[r.layer][r.slot] = r.expert
    descriptors, queue, _ = src.audit.state_before(rows[: cut + 1])
    check(not queue and all(s in (0, 2) and not c for _, _, s, c in descriptors), "drain")
    final = [[descriptors[40 * layer + i][0] for i in range(40)] for layer in range(36)]
    for pools in (initial, final):
        for pool in pools:
            live = [e for e in pool if e >= 0]
            check(len(live) == len(set(live)), "duplicate physical resident")
    waves = []
    site = None
    for r in rows:
        here = (r.call, r.tile, r.layer, r.wave)
        if r.kind == 9:
            check(site is None, "overlap")
            site, demand = here, []
        elif r.kind == 10:
            check(site == here and r.expert not in demand, "ordered demand")
            demand.append(r.expert)
        elif r.kind == 23:
            check(site == here, "end of wave")
            if demand:
                waves.append((r.call, r.layer, tuple(demand)))
            site = None
    check(site is None and {c for c, _, _ in waves} == set(range(1, 49)), "48 calls")
    return initial, final, waves


def compulsory(initial, final, waves, bank, restore):
    needed = {(layer, e) for call, layer, wave in waves if call <= 2 for e in wave}
    if restore:
        needed.update((layer, e) for layer, pool in enumerate(final) for e in pool if e >= 0)
    start = {(layer, e) for layer, pool in enumerate(initial) for e in pool if e >= 0}
    return len(needed - start - bank)


def evaluate(initial, final, waves, bank, prefer_backed, restore, budgets):
    pools = [Pool(p) for p in initial]
    prefill, decode, reset = Counter(), Counter(), Counter()
    at_decode = False
    for tick, (call, layer, wave) in enumerate(waves, 1):
        if call > 2 and not at_decode:
            if restore:
                for i, pool in enumerate(pools):
                    pool.restore(i, final[i], bank, tick, reset)
            at_decode = True
        pools[layer].wave(layer, wave, bank, prefer_backed, tick, prefill if call <= 2 else decode)
    loads = prefill["disk"] + reset["disk"]
    floor = compulsory(initial, final, waves, bank, restore)
    check(loads >= floor, "distinct-key lower bound")
    payload = loads * PAYLOAD
    return dict(
        prefill=prefill,
        decode=decode,
        restore=reset,
        restore_required=restore,
        prefill_disk_bytes=payload,
        compulsory_cold_keys=floor,
        decode_read_gate=decode["disk"] <= 872,
        scenario={
            n: dict(
                volume_gate=payload <= budget,
                excess_bytes=payload - budget,
                min_useful_GBps=4.5 * payload / budget,
                joint=payload <= budget and decode["disk"] <= 872,
            )
            for n, budget in budgets.items()
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("part", "model", "inventory", "prepared-dir", "score-dir", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        prior = src.pinned(HERE.parent / "t1_router_window/evidence/receipt.json", ROUTER_RECEIPT)
        score = src.pinned(a.score_dir / "receipt.json", prior["local_sha256"])
        seal = src.pinned(a.prepared_dir / "receipt.json", prior["prepare_sha256"])
        check(
            src.sha(a.prepared_dir / "selection.json") == seal["selection_sha256"], "bank identity"
        )
        data = src.load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
        check(data.journal == prior["source_journal_sha256"], "same process")
        work = router["consumed"](data.rows, data.meta)
        check(len(work) == prior["R0"]["totals"]["consumed"], "all consumers")
        initial, final, waves = inputs(data.rows)
        warm = set(map(tuple, data.prefix["capacities"]["353"]["ordered_keys"]))
        check(len(warm) == 353, "bank capacity")
        budgets = score["results"]["current"]["budgets"]
        arms = {}
        for name, bank, prefer in (
            ("lru", set(), False),
            ("lru_ram", warm, False),
            ("evict_backed_first", warm, True),
        ):
            arms[name] = {
                mode: evaluate(initial, final, waves, bank, prefer, restore, budgets)
                for mode, restore in (("carry", False), ("restore", True))
            }
        decisions = [row["scenario"]["47"]["joint"] for row in arms["evict_backed_first"].values()]
        result = dict(
            status="GO_FIXTURE_ONLY" if any(decisions) else "NO_GO_CONDITIONAL",
            arms=arms,
            budgets=budgets,
            journal_sha256=data.journal,
            R0=dict(prefill=1263, decode=1091),
            r0_receipt_sha256=ROUTER_RECEIPT,
        )
    except (ValueError, KeyError, IndexError, OSError, StopIteration) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(
        program_sha256=src.sha(Path(__file__)), protocol_sha256=src.sha(HERE / "protocol.md")
    )
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
