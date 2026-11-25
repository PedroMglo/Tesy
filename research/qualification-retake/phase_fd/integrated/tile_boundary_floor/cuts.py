"""Resolve the minimum paid wave admissions at every subset of the four internal cuts."""

import argparse
import json
from itertools import combinations, pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
base = run_path(str(HERE / "floor.py"))
src, need, PAY = (base[k] for k in ("src", "need", "PAY"))
ORACLE = HERE.parent / "t1_primary_victim/oracle.py"
METHOD = "47fa13e93825f7a4acb3c08fb30591c161b9719f494664eabe1c1a88d24c4542"
FLOOR = "31c680ae31f11c7130ef3f71bf973ff69914bea7735cff5b1274bbf3ce980706"
CONTROL = "727f262d965b40a410d967d73d4c7fadb75161776ddadd47321d49dee59b9db6"
INTERNAL = frozenset(range(2, 6))  # consecutive cuts after the 1st to 4th tile of call 148


def observed(rows):
    starts = {}
    for i, r in enumerate(rows):
        if r.kind == 9 and r.call in (74, 75):
            starts.setdefault((r.call, r.tile), i)
    need(list(starts) == base["GEOMETRY"], "tile order")
    end = next(i for i, r in enumerate(rows) if r.kind == 1 and r.call == 76)
    snapshots = []
    for index in [*starts.values(), end]:
        ready, loading, queue = base["boundary"](rows, index)
        need(len(ready) == 1440 and not loading and not queue, "non-drained cut")
        layers = [{e for owner, e in ready if owner == layer} for layer in range(36)]
        need(all(len(layer) == 40 for layer in layers), "layer occupancy")
        snapshots.append(layers)
    # bucket 6 is the entire decode only. The full PFJ auditor qualifies every nonempty group.
    cells = [[[] for _ in range(36)] for _ in range(7)]
    cell = None
    for r in rows[next(iter(starts.values())) :]:
        if r.kind == 9:
            need(cell is None, "nested remap")
            phase = list(starts).index((r.call, r.tile)) if r.call <= 75 else 6
            cell = (phase, r.layer, [])
        elif r.kind == 10:
            need(cell is not None and cell[1] == r.layer, "misplaced demand")
            cell[2].append(r.expert)
        elif r.kind == 23:
            need(cell is not None and cell[1] == r.layer, "misplaced exit")
            if cell[2]:
                cells[cell[0]][cell[1]].append(cell[2])
            cell = None
    need(cell is None and sum(map(len, cells[6])) == 46 * 36, "decode groups")
    return cells, snapshots


def fewest_layers(fixed, free, limit):
    """Independent per-layer pools make the sorted deltas a tight count in this relaxation."""
    need(len(free) == len(fixed) and all(a >= b for a, b in zip(fixed, free, strict=True)), "delta")
    n = sum(fixed)
    gains = sorted((a - b for a, b in zip(fixed, free, strict=True)), reverse=True)
    for k in range(len(gains) + 1):
        if n <= limit:
            return k
        if k < len(gains):
            n -= gains[k]
    return None


def evaluate(cells, snapshots, bank, budgets, floor, paid_minimum):
    layer_banks = [{e for owner, e in bank if owner == layer} for layer in range(36)]
    costs = {}
    for lo in range(6):
        for hi in range(lo + 1, 7):
            by_layer = []
            for layer, backed in enumerate(layer_banks):
                groups = [wave for cell in cells[lo:hi] for wave in cell[layer]]
                groups.append(sorted(snapshots[hi][layer]))
                by_layer.append(paid_minimum(groups, 40, snapshots[lo][layer], backed))
            costs[lo, hi] = by_layer

    def total(cuts):
        intervals = [costs[pair] for pair in pairwise(sorted(cuts))]
        return list(map(sum, zip(*intervals, strict=True)))

    decode = [
        paid_minimum(cells[6][layer], 40, snapshots[-1][layer], backed)
        for layer, backed in enumerate(layer_banks)
    ]
    full = total(range(7))
    external = total((0, 1, 6))
    final_only = total((0, 6))
    for key, loads in (
        ("tiles", full),
        ("external_calls", external),
        ("first_decode_only", final_only),
    ):
        need(sum(loads) >= floor[key]["reads"], "compulsory volume")
    loads = {}
    table = []
    for count in range(5):
        for release in combinations(sorted(INTERNAL), count):
            released = frozenset(release)
            by_layer = total(({0, 1, 6} | INTERNAL) - released)
            for k in released:
                need(
                    all(a >= b for a, b in zip(loads[released - {k}], by_layer, strict=True)),
                    "removing a requirement increased a finite-capacity minimum",
                )
            loads[released] = by_layer
            table.append(
                dict(
                    released_after_tile_of_148=[k - 1 for k in release],
                    cpu=sum(by_layer[:25]),
                    cuda=sum(by_layer[25:]),
                    total=sum(by_layer),
                )
            )

    return dict(
        cuts=table,
        decode_cpu=sum(decode[:25]),
        decode_cuda=sum(decode[25:]),
        decode_minimum=sum(decode),
        prefill_final_only=sum(final_only),
        all_four_free_only_cpu=sum(external[:25]) + sum(full[25:]),
        all_four_free_only_cuda=sum(full[:25]) + sum(external[25:]),
        scenarios={
            key: dict(
                fewest_free_layers_for_prefill=fewest_layers(full, external, budget // PAY),
                fewest_free_cuts_for_prefill=min(
                    (
                        len(r["released_after_tile_of_148"])
                        for r in table
                        if r["total"] * PAY <= budget
                    ),
                    default=None,
                ),
                feasible_cut_subsets=sum(r["total"] * PAY <= budget for r in table),
                best_payload_margin_bytes=budget - sum(external) * PAY,
                best_required_GBs_at_preexisting_budget=4.5 * sum(external) * PAY / budget,
                joint_headroom=sum(external) * PAY <= budget and sum(decode) <= 872,
            )
            for key, budget in budgets.items()
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("part", "selection", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        need(src.sha(HERE / "cuts-protocol.md") == METHOD, "prospective method")
        need(
            src.sha(ORACLE) == "b655c173fb9dce5264e105adcd9abf6f433a9dfad4dba93760b7f22364cdf023",
            "paid oracle",
        )
        floor = src.pinned(HERE / "receipt.json", FLOOR)
        ref = src.pinned(ORACLE.parent / "evidence/oracle.json", CONTROL)
        rows, banks, prior = base["load_inputs"](a.part, a.selection)
        cells, snaps = observed(rows)
        paid = run_path(str(ORACLE))["paid_minimum"]
        arms = {
            name: evaluate(
                cells, snaps, keys, prior["conditional_volume_budgets"], floor["arms"][name], paid
            )
            for name, keys in banks.items()
        }
        need(arms["empty"]["cuts"][0]["total"] <= 1263, "more expensive than R0 witness")
        for arm, name in (("empty", "no_bank"), ("victims", "recency353")):
            old = ref["arms"][name]["total"]
            need(
                (arms[arm]["prefill_final_only"], arms[arm]["decode_minimum"])
                == (old["prefill_r0_exit"], old["decode_from_r0"]),
                "independent endpoint oracle",
            )
        result = dict(
            status="REPRODUCED_40_SLOT_OFFLINE_FRONTIER",
            protocol_sha256=METHOD,
            program_sha256=src.sha(Path(__file__)),
            distinct_floor_sha256=FLOOR,
            full_oracle_sha256=CONTROL,
            journal_sha256=prior["journal_sha256"],
            selection_sha256=base["SELECTION"],
            arms=arms,
            model_forwards=0,
            weight_reads=0,
        )
    except (ValueError, KeyError, IndexError, StopIteration, OSError) as exc:
        result = dict(
            status="NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            reason=f"{type(exc).__name__}: {exc}",
        )
    tmp = out / "report.tmp"
    with tmp.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.rename(out / "receipt.json")
    print(result["status"])
    return int(result["status"] != "REPRODUCED_40_SLOT_OFFLINE_FRONTIER")


if __name__ == "__main__":
    raise SystemExit(main())
