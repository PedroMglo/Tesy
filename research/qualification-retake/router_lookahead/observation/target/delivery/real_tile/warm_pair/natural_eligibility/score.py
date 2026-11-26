"""Reopen two qualified natural sessions and count empty primary pools at T2."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = next(p for p in HERE.parents if p.name == "qualification-retake")
PACK = Q / "igpu_resident_rank/request_budget/device/pack_native"
PARENT = run_path(str(PACK / "natural_trace/prefill_retention/request_cost/score.py"))
AUTH, CHAIN, T = (PARENT[k] for k in ("Q", "CHAIN", "T"))
check, digest, pinned = (PARENT[k] for k in ("check", "digest", "pinned"))
EMPTY, LOADING, READY = range(3)


def transition(old, row):
    expert, gen, state = old
    if row.kind == 11:
        check(
            row.a == expert
            and row.gen == gen + 1
            and state in (READY, EMPTY)
            and row.expert in range(128)
            and row.expert != expert,
            "reserve victim/generation/old state",
        )
        return row.expert, row.gen, LOADING
    check(row.kind == 17 and old == (row.expert, row.gen, LOADING), "publish binding")
    return row.expert, row.gen, READY


def distribution(values):
    return dict(sorted(Counter(values).items()))


def group(layer, tiers):
    if layer == 0:
        return "L0_no_predecessor"
    if layer == 1:
        return "CPU_L1"
    return "CPU_L2_24" if tiers[layer] == "CPU" else "CUDA_L25_35"


def census(rows, tiers):
    host = CHAIN["NATURAL"]["host_trace"](rows)
    slots = {k: v[:3] for k, v in AUTH["bindings"](rows).items()}
    counts = [Counter(slots[layer, s][2] for s in range(40)) for layer in range(36)]
    initial = {
        tier: {
            label: distribution(counts[layer][state] for layer in range(36) if tiers[layer] == tier)
            for state, label in enumerate(("empty_slots", "loading_slots", "ready_slots"))
        }
        for tier in ("CPU", "CUDA0")
    }
    least_bound = [40 - x[EMPTY] for x in counts]
    least_ready = [x[READY] for x in counts]
    # A nonempty initial pool cannot become empty on a valid reserve or publish.
    # Keep the actual extrema as an independent check, including in-flight waves.
    waves, sites, routed, empty_waves = Counter(), defaultdict(set), defaultdict(set), Counter()
    first_wave_occupancy, reservations, publications = defaultdict(Counter), Counter(), Counter()
    for e in rows:
        if e.kind in (18, 28) or e.kind not in range(1, 31):
            raise ValueError("uncovered service transition or observation type")
        if e.kind not in (9, 11, 17, 27):
            continue
        phase = "call5" if e.call == 1 else "call148" if e.call == 2 else "decode"
        layer = e.layer
        key = phase, group(layer, tiers)
        occupied = 40 - counts[layer][EMPTY]
        if e.kind == 9:
            waves[key] += 1
            empty_waves[key] += occupied == 0
            site = e.call, e.tile, layer
            if site not in sites[key]:
                first_wave_occupancy[key][occupied] += 1
                sites[key].add(site)
        elif e.kind == 27:
            routed[key].add((e.call, e.tile, layer))
        else:
            where = layer, e.slot
            old = slots[where]
            new = transition(old, e)
            counts[layer][old[2]] -= 1
            counts[layer][new[2]] += 1
            slots[where] = new
            current = 40 - counts[layer][EMPTY]
            check(current >= occupied, "nonmonotonic occupancy in manager")
            least_bound[layer] = min(least_bound[layer], current)
            least_ready[layer] = min(least_ready[layer], counts[layer][READY])
            if e.kind == 11:
                reservations["replace_ready" if old[2] == READY else "fill_empty"] += 1
            else:
                publications["ready"] += 1
    check(sum(reservations.values()) == publications["ready"] == 2354, "all demanded service")
    check(set(waves) == set(sites) and not any(x[LOADING] for x in counts), "end or coverage")
    return {
        "route": host["route"],
        "entry_per_layer_histogram": initial,
        "minimum_bound_slots_by_layer": least_bound,
        "minimum_ready_slots_by_layer": least_ready,
        "possibly_empty_cpu_plus1_layers": [
            layer for layer in range(1, 25) if not least_bound[layer]
        ],
        "possibly_empty_cuda_plus1_layers": [
            layer for layer in range(25, 36) if not least_bound[layer]
        ],
        "reservations": reservations,
        "publications": publications["ready"],
        "cells": [
            dict(
                phase=k[0],
                destination=k[1],
                remap_callbacks=waves[k],
                sites=len(sites[k]),
                sites_with_ranks=len(routed[k]),
                empty_at_remap=empty_waves[k],
                occupied_at_first_wave_histogram=first_wave_occupancy[k],
            )
            for k in waves
        ],
    }


def arm(archive, label):
    name, fsha, msha = PARENT["SOURCES"][label]
    part = archive / ("part-" + label[1:])
    root = part / name
    pinned(part / "manifest.json", msha)
    if label == "P106":
        _, rows, tiers, proof = AUTH["read_new"](root, fsha)
        jsha = proof["journal_sha256"]
    else:
        _, _, receipt, audit = CHAIN["chain"](root, fsha)
        on = root / "ON"
        reopened = CHAIN["NATURAL"]["audit_arm"](
            on, receipt, receipt["pack_events"]["before_second_ns"]
        )
        check(
            json.loads(json.dumps(reopened)) == audit and audit["jobs"]["eligible_clean_run"],
            "historical service",
        )
        rows, header = T["PFJ"]["read_journal"](on / "raw/events.pfj")
        log = on / "raw" / receipt["native_ids"]["raw_stderr_file"]
        check(digest(log) == receipt["native_ids"]["stderr_sha256"], "producer log")
        tiers, _ = T["mapping"](log.read_bytes(), rows)
        jsha = header["journal_sha256"]
    return {
        "family_sha256": fsha,
        "manifest_sha256": msha,
        "journal_sha256": jsha,
        **census(rows, tiers),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    report = {
        "status": "FAIL_PRESERVED",
        "protocol_sha256": digest(HERE / "protocol.md"),
        "source_sha256": digest(HERE / "score.py"),
    }
    try:
        observations = {label: arm(a.archive, label) for label in ("P97", "P106")}
        report["observations"] = observations
        check(observations["P97"]["route"] == observations["P106"]["route"], "trajectory mismatch")
        exceptions = any(x["possibly_empty_cpu_plus1_layers"] for x in observations.values())
        report["status"] = (
            "POSSIBLE_EMPTY_DESTINATION" if exceptions else "NO_GO_EMPTY_ONLY_CPU_PLUS1_NATURAL_T2"
        )
    except (OSError, ValueError, AssertionError, KeyError) as exc:
        report["reason"] = str(exc)
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(report["status"])
    return int(report["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
