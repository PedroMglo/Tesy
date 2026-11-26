"""Exact minimum disk admissions with zero-cost reloads for a fixed RAM bank."""

import argparse
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
replay = run_path(str(HERE / "screen.py"))
src = replay["src"]
minimum = run_path(str(HERE.parents[2] / "cache_bound.py"))["minimum"]
PAYLOAD = replay["PAYLOAD"]
CAUSAL = "5a98dfe45eae6900c68b8ca6bea899d3222c1769f3ca99ccf1ab79eddd53c796"


def paid_minimum(waves, capacity, start, bank):
    """Unique temporary pins for free reloads leave the same space for paid pages."""
    first_temporary = 128
    next_temporary = first_temporary
    transformed = []
    for group in waves:
        src.need(len(set(group)) == len(group) and all(0 <= k < 128 for k in group), "group")
        new_group = []
        for k in group:
            if k in bank:
                new_group.append(next_temporary)
                next_temporary += 1
            else:
                new_group.append(k)
        transformed.append(new_group)
    total = minimum(transformed, capacity, initial=start - bank)
    return total - (next_temporary - first_temporary)


def report(initial, final, waves, bank, budgets):
    phases = [{"prefill": [], "decode": []} for _ in initial]
    for call, layer, members in waves:
        phases[layer]["prefill" if call <= 2 else "decode"].append(members)
    tiers = {"cpu": Counter(), "cuda": Counter()}
    for layer, phases_in_layer in enumerate(phases):
        tier = tiers["cpu" if layer < 25 else "cuda"]
        backed = {expert for owner, expert in bank if owner == layer}
        start = set(initial[layer]) - {-1}
        required = set(final[layer]) - {-1}
        pf = phases_in_layer["prefill"]
        tier["prefill_free_exit"] += paid_minimum(pf, 40, start, backed)
        tier["prefill_r0_exit"] += paid_minimum([*pf, sorted(required)], 40, start, backed)
        tier["decode_from_r0"] += paid_minimum(phases_in_layer["decode"], 40, required, backed)
    total = tiers["cpu"] + tiers["cuda"]
    payload = total["prefill_r0_exit"] * PAYLOAD
    floor = replay["compulsory"](initial, final, waves, bank, True)
    src.need(max(floor, total["prefill_free_exit"]) <= total["prefill_r0_exit"], "floor")
    return dict(
        tiers=tiers,
        total=total,
        restore_distinct_floor=floor,
        scenarios={
            n: dict(
                prefill_bytes=payload,
                margin_bytes=b - payload,
                joint=payload <= b and total["decode_from_r0"] <= 872,
            )
            for n, b in budgets.items()
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for s in (
        "part",
        "model",
        "inventory",
        "prepared-dir",
        "score-dir",
        "causal-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + s, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        causal = src.pinned(a.causal_dir / "receipt.json", CAUSAL)
        kval = src.pinned(
            HERE.parent / "t1_router_window/evidence/receipt.json", replay["ROUTER_RECEIPT"]
        )
        score = src.pinned(a.score_dir / "receipt.json", kval["local_sha256"])
        seal = src.pinned(a.prepared_dir / "receipt.json", kval["prepare_sha256"])
        src.need(
            src.sha(a.prepared_dir / "selection.json") == seal["selection_sha256"]
            and causal["budgets"] == score["results"]["current"]["budgets"],
            "pinned preparation",
        )
        data = src.load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
        src.need(
            data.journal == causal["journal_sha256"] == kval["source_journal_sha256"], "journal"
        )
        start, required, waves = replay["inputs"](data.rows)
        bank = set(map(tuple, data.prefix["capacities"]["353"]["ordered_keys"]))
        src.need(len(bank) == 353, "bank")
        tables = {}
        for name, keys, controls in (
            ("no_bank", set(), ["lru"]),
            ("recency353", bank, ["lru_ram", "evict_backed_first"]),
        ):
            row = report(start, required, waves, keys, causal["budgets"])
            for arm in controls:
                ref = causal["arms"][arm]["restore"]
                src.need(
                    row["restore_distinct_floor"] == ref["compulsory_cold_keys"]
                    and row["total"]["prefill_r0_exit"] <= ref["prefill_disk_bytes"] // PAYLOAD
                    and row["total"]["decode_from_r0"] <= ref["decode"]["disk"],
                    "causal witness",
                )
            tables[name] = row
        status = (
            "HEADROOM_ONLY" if tables["recency353"]["scenarios"]["47"]["joint"] else "NO_GO_VOLUME"
        )
        result = dict(status=status, arms=tables, causal_sha256=CAUSAL, journal_sha256=data.journal)
    except (ValueError, KeyError, IndexError, OSError, StopIteration) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(
        program_sha256=src.sha(Path(__file__)), protocol_sha256=src.sha(HERE / "oracle-protocol.md")
    )
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
