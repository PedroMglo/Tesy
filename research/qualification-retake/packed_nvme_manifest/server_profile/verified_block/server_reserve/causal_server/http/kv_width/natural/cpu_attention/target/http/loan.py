"""Price causal slot lending against identical native work, including every repair."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "slots.py"))
B, C, G, R, need, sha, save = (S[k] for k in ("B", "C", "G", "R", "need", "sha", "save"))
METHOD = "d51bc20ca2fd995cea870c9578f6096b3231d02b68622c0aeb3791ceda0d54b8"
PREVIOUS = "7d3e20f41f8e1c92add2e7bad358a1c61026950f2c145567f496c179d97c8063"
PRICING = "b089c311a6b2ff9026b2dba8c061018583b3bcaea261f7743ccb9b2d7ad1e063"


@dataclass
class Loan:
    carrier: tuple
    source: tuple
    first_tile: int
    served: bool = False


class PoolReplay:
    def __init__(self, initial):
        self.logical = initial.copy()
        self.payload = {loc: k[3] for loc, k in initial.items()}
        self.positions = defaultdict(list)
        for layer, slot in sorted(initial):
            self.positions[layer].append(slot)
        self.active = {}
        self.last_capture = {}
        self.frequency = Counter()
        self.last_seen = {}
        self.first_tile = {}
        self.groups = defaultdict(Counter)
        self.decisions = []

    def capture(self, index, wave, reserved, count):
        _, tile, layer, _ = wave.site
        if tile == 5 or self.last_capture.get(layer) == tile:
            return
        prior = [old for old, _ in wave.reservations if C["expert"](old) in self.last_seen]
        slots = [s for s in self.positions[layer] if s not in reserved and s not in wave.readers]
        if not prior or not slots:
            return
        old = max(
            prior, key=lambda x: (self.frequency[C["expert"](x)], self.last_seen[C["expert"](x)])
        )
        slot = min(
            slots, key=lambda s: (self.last_seen.get(C["expert"](self.logical[layer, s]), -1), s)
        )
        carrier = self.logical[layer, slot]
        need(
            self.payload[old[:2]] == old[3] and self.payload[carrier[:2]] == carrier[3],
            "capture inputs",
        )
        self.payload[carrier[:2]] = old[3]
        self.active[layer] = Loan(carrier, old, self.first_tile[C["expert"](old)])
        self.last_capture[layer] = tile
        self.decisions.append((index, "save", old, carrier))
        count["saves"] += 1

    def repair(self, index, layer, count, reason):
        loan = self.active.pop(layer)
        need(self.logical[loan.carrier[:2]] == loan.carrier, "owed generation")
        self.payload[loan.carrier[:2]] = loan.carrier[3]
        count[reason] += 1
        self.decisions.append((index, reason, loan.carrier))

    def existing(self, index, wave, reserved, loan, count):
        _, tile, layer, _ = wave.site
        slot = loan.carrier[1]
        if slot in reserved:
            self.active.pop(layer)
            count["expired_on_original_fill"] += 1
            self.decisions.append((index, "overwrite", loan.carrier))
        elif slot in wave.readers:
            self.repair(index, layer, count, "reader_repairs")
        elif tile > loan.first_tile and not loan.served:
            for _, new in wave.reservations:
                if new[3] == loan.source[3]:
                    need(
                        self.logical[loan.carrier[:2]] == loan.carrier
                        and self.payload[loan.carrier[:2]] == new[3],
                        "rescue identity",
                    )
                    self.decisions.append((index, "hit", new, loan.carrier))
                    loan.served = True
                    count["hits"] += 1
                    return new
        return None

    def step(self, index, wave, on):
        _, tile, layer, _ = wave.site
        count = self.groups[tile, "CPU" if layer < 25 else "CUDA0"]
        reserved = {new[1] for _, new in wave.reservations}
        hit = None
        if on:
            if layer in self.active:
                hit = self.existing(index, wave, reserved, self.active[layer], count)
            else:
                self.capture(index, wave, reserved, count)
        for old, new in wave.reservations:
            need(self.logical[old[:2]] == old, "unchanged original reservation")
            self.logical[new[:2]] = new
            if new == hit:
                self.payload[new[:2]] = self.payload[self.active[layer].carrier[:2]]
            else:
                self.payload[new[:2]] = new[3]
                count["original_disk"] += 1
        for key in wave.readers.values():
            need(
                self.logical[key[:2]] == key and self.payload[key[:2]] == key[3],
                "incorrect graph operand",
            )
            count["reader_slots"] += 1
        for key in wave.demands:
            expert = C["expert"](key)
            self.last_seen[expert] = index
            self.first_tile.setdefault(expert, tile)
            self.frequency[expert] += 1

    def finish(self, final, end):
        for layer in sorted(self.active.copy()):
            count = self.groups[5, "CPU" if layer < 25 else "CUDA0"]
            self.repair(end, layer, count, "terminal_repairs")
        need(
            self.logical == final
            and all(self.payload[loc] == key[3] for loc, key in final.items()),
            "handoff to decode",
        )
        total = Counter()
        for group in self.groups.values():
            total.update(group)
        need(
            total["saves"]
            == total["expired_on_original_fill"]
            + total["reader_repairs"]
            + total["terminal_repairs"]
            and total["hits"] <= total["saves"],
            "loan conservation",
        )

        def amounts(t):
            paid = t["reader_repairs"] + t["terminal_repairs"]
            return dict(
                **t,
                read_jobs=t["original_disk"] + paid,
                repairs=paid,
                net_reads_saved=t["hits"] - paid,
                slot_copy_payload_B=(t["saves"] + t["hits"]) * B["PAYLOAD"],
                unused_captures=t["saves"] - t["hits"],
            )

        tier_totals = {}
        for tier in ("CPU", "CUDA0"):
            tier_totals[tier] = amounts(
                sum((v for (_, k), v in self.groups.items() if k == tier), Counter())
            )
        return dict(
            total=amounts(total),
            tiers=tier_totals,
            tiles=[dict(tile=t, tier=k, **v) for (t, k), v in sorted(self.groups.items())],
            decisions_sha256=hashlib.sha256(
                json.dumps(self.decisions, separators=(",", ":")).encode()
            ).hexdigest(),
        )


def replay(initial, waves, final, on):
    p = PoolReplay(initial)
    for i, wave in enumerate(waves):
        p.step(i, wave, on)
    return p.finish(final, len(waves))


def fixture():
    keys = [(0, i, 1, e) for i, e in enumerate((7, 5, 6))]
    a, b, c = keys
    x, y, z = (0, 0, 2, 9), (0, 2, 2, 7), (0, 1, 2, 10)
    start = {k[:2]: k for k in keys}
    end = {k[:2]: k for k in (x, z, y)}
    waves = [S["Wave"]((2, t, 0, 0)) for t in (1, 1, 2, 2)]
    waves[0].demands, waves[0].readers = [a], {0: a}
    for wave, old, new in zip(waves[1:], (a, c, b), (x, y, z), strict=True):
        wave.reservations = [(old, new)]
        wave.demands, wave.readers = [new], {new[1]: new}
    f = PoolReplay(start)
    for i, wave in enumerate(waves[:2]):
        f.step(i, wave, True)
    prefix = f.decisions.copy()
    partial = f.finish(f.logical.copy(), 2)
    good = replay(start, waves, end, True)["total"]
    need(
        good["hits"] == good["expired_on_original_fill"] == 1
        and good["repairs"] == 0
        and partial["total"]["terminal_repairs"] == 1,
        "rescue/overwrite/closure",
    )
    waves[2].readers[1] = b
    adverse = PoolReplay(start)
    for i, wave in enumerate(waves):
        adverse.step(i, wave, True)
    need(
        prefix == adverse.decisions[: len(prefix)]
        and adverse.finish(end, 4)["total"]["reader_repairs"] == 1,
        "prefix or parking fallback",
    )
    return ["later_rescue", "overwrite", "terminal_repair", "parking_repair", "unchanged_prefix"]


def study(a):
    head, tree = G["tree"](G["REPO"])
    need(head == a.commit and sha(HERE / "loan-protocol.md") == METHOD, "sealed policy")
    fixed = G["read"](a.slots / "result.json", PREVIOUS)
    op = G["read"](a.pricing / "result.json", PRICING)
    need(op["schedule_sha256"] == PREVIOUS, "operator provenance")
    data, steps = R["cases"](a)
    tiers = None
    prior = None
    for label in ("P106", "P97"):
        rows, tiers, ids = B["trace_arm"](a, label, tiers, data, steps)
        initial, waves, final = S["gather"](rows)
        need(
            S["content_hash"](initial) == fixed["matched"]["initial_sha256"]
            and S["content_hash"](final) == fixed["matched"]["decode_sha256"],
            "exact endpoint generations",
        )
        control = replay(initial, waves, final, False)
        candidate = replay(initial, waves, final, True)
        off, on = control["total"], candidate["total"]
        need(
            off["reader_slots"]
            == on["reader_slots"]
            == fixed["matched"]["control"]["protected_wave_slots"]
            and off["read_jobs"] == fixed["matched"]["control"]["disk"]
            and off["read_jobs"] - on["read_jobs"] == on["net_reads_saved"],
            "ablation",
        )
        obs = dict(target_ids=ids, control=control, candidate=candidate)
        need(prior is None or obs == prior, "replicas")
        prior = obs
    n = on["net_reads_saved"]
    return dict(
        status="NO_GO_CAUSAL_READ_REDUCTION" if n <= 0 else "TRACE_DERIVED_PARTIAL_READ_SAVING",
        protocol_sha256=METHOD,
        commit=head,
        tree=tree,
        fixture=fixture(),
        arms=["P106", "P97"],
        **obs,
        signed_aligned_reads_saved_B=n * B["WINDOW"],
        max_exposed_cost_partial_s=n * B["WINDOW"] / B["IO"]["RATE"],
        zero_new_decode_cost_margin_B={
            k: n * B["WINDOW"] - v["free"]["required"] for k, v in fixed["pricing"].items()
        },
        model_starts=0,
        http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "pricing", "slots", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        r = study(a)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", commit=a.commit, error=f"{type(exc).__name__}: {exc}")
    save(a.new_output_dir / "result.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
