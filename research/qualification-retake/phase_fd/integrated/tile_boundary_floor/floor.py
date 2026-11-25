"""Bound disk reads needed between immutable primary-residency snapshots in the C281 prefill."""

import argparse
import json
from collections import Counter
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
bank_api = run_path(str(HERE.parent / "t1_source_bank/screen.py"))
src, fd, need = (bank_api[key] for key in ("src", "fd", "need"))
PAY, PACK = bank_api["PAY"], bank_api["PACK"]
METHOD = "46b19dcbf27495d8bca96369b31d1afb970093d47287e85c63b72f9dcaace2a7"
SELECTION = "27f03c1242123e82c9b8c77bd54a0c3479cd628e04451b45b3bfccc030656c15"
PRIOR = "f2e1232d2466835931bdbe43420a61cb05fd0d473705c42ea5c5fbcabe87f049"
GEOMETRY = [(74, 1), *((75, tile) for tile in range(1, 6))]


def boundary(rows, index):
    slots, fifo, _ = src.audit.state_before(rows[:index])
    ready, loading = set(), set()
    for i, (expert, _, state, _) in enumerate(slots):
        if state:
            key = (i // 40, expert)
            need(key not in ready and key not in loading, "duplicate occupied expert")
            (ready if state == 2 else loading).add(key)
    return ready, loading, len(fifo)


def compulsory(demand, exit_ready, entry_ready, entry_loading, bank):
    """Grant the incoming and bank bytes for free, even if a read is still running."""
    return (demand | exit_ready) - entry_ready - entry_loading - bank


def price(n, budget):
    gap = n * PAY - budget
    return dict(
        payload_margin_bytes=-gap,
        pack_margin_bytes=budget - n * PACK,
        payload_margin_ms_at_4_5_GBs=-gap / 4_500_000,
        max_reads=budget // PAY,
        decision="NO_GO_CONDITIONAL" if gap > 0 else "HEADROOM_ONLY",
    )


def load_inputs(part, selection_path):
    bank_api["pin_programs"]()
    need(src.sha(HERE / "protocol.md") == METHOD, "changed protocol")
    files = src.manifest(part)
    root = part / src.ARM
    src.pinned(root / "receipt.json", src.FAIL)
    rows, header = fd.read_journal(root / "raw/events.pfj")
    need(
        header["journal_sha256"]
        == bank_api["JOURNAL"]
        == files[src.ARM + "/raw/events.pfj"]["sha256"],
        "wrong trace",
    )
    prior = src.pinned(HERE.parent / "t1_source_bank/receipt.json", PRIOR)
    seal = src.pinned(selection_path, SELECTION)
    need(
        prior["selection_file_sha256"] == SELECTION
        and seal == json.loads(json.dumps(bank_api["prepare"](part))),
        "causal bank identity",
    )
    banks = {"empty": set()}
    for label in ("victims", "published"):
        keys = set(map(tuple, seal["selection"][label]))
        need(len(keys) == bank_api["K"], "bank size")
        banks[label] = keys
    audited = src.audit.conservation(rows, header, None, 74)
    calls = audited["calls"][73:76]
    need(
        [(r["tokens"], r["tiles"]) for r in calls] == [(5, [5]), (148, [32] * 4 + [20]), (1, [1])],
        "prefill geometry",
    )
    return rows, banks, prior


def score(part, selection):
    rows, banks, prior = load_inputs(part, selection)
    # The first host remap is the mutex-sequenced cut. All six wave lists are audited above.
    starts = {}
    for i, r in enumerate(rows):
        if r.kind == 9 and r.call in (74, 75):
            starts.setdefault((r.call, r.tile), i)
    need(list(starts) == GEOMETRY, "tile order")
    decode = next(i for i, r in enumerate(rows) if r.kind == 1 and r.call == 76)
    enter = next(i for i, r in enumerate(rows) if r.kind == 1 and r.call == 74)
    cuts = [*starts.values(), decode]
    need(not any(r.kind in (10, 11, 17) for r in rows[enter : cuts[0]]), "work before first cut")
    snapshots = [boundary(rows, i) for i in cuts]
    # The common final descriptor was verified in both independent nominal runs.
    final_slots = src.audit.state_before(rows[:decode])[0]
    entry_control = src.pinned(
        HERE.parent / "t1_manager_bank/decode_entry/receipt.json",
        "def18d5ad7e20a7c47033e690ed8da64c3ff6066879b97db5ebadf3fc8f680e2",
    )
    for field, key in enumerate(("slot_expert", "slot_generation", "slot_state", "slot_claim")):
        view = [[s[field] for s in final_slots[i : i + 40]] for i in range(0, 1440, 40)]
        need(
            entry_control["cut_fields"][key]["ordered_sha256"] == [src.audit.digest(view)] * 2,
            "first decode descriptor differs: " + key,
        )
    final_digest = src.audit.digest(final_slots)
    groups = {"tiles": range(7), "external_calls": (0, 1, 6), "first_decode_only": (0, 6)}
    arms = {}
    for label, bank in banks.items():
        projections = {}
        for name, indices in groups.items():
            blocks = []
            for lo, hi in pairwise(indices):
                interval = rows[cuts[lo] : cuts[hi]]
                demand = {(r.layer, r.expert) for r in interval if r.kind == 10}
                admissions = Counter((r.layer, r.expert) for r in interval if r.kind == 11)
                i_ready, i_loading, _ = snapshots[lo]
                f_ready, _, _ = snapshots[hi]
                paid = compulsory(demand, f_ready, i_ready, i_loading, bank)
                need(paid <= admissions.keys(), "charged key has no physical reservation")
                cpu = sum(layer < 25 for layer, _ in paid)
                blocks.append(
                    dict(
                        range_of_tiles=[lo + 1, hi],
                        rank_demand_distinct=len(demand),
                        r0_reservations=admissions.total(),
                        disk_floor_cpu=cpu,
                        disk_floor_cuda=len(paid) - cpu,
                        restore_only=len(paid - demand),
                    )
                )
            n = sum(b["disk_floor_cpu"] + b["disk_floor_cuda"] for b in blocks)
            need(sum(b["r0_reservations"] for b in blocks) == 1263, "R0 prefill accounting")
            projections[name] = dict(
                reads=n,
                payload_bytes=n * PAY,
                pack_bytes=n * PACK,
                intervals=blocks,
                scenarios={k: price(n, v) for k, v in prior["conditional_volume_budgets"].items()},
            )
        old_arm = {
            "empty": "lru_off",
            "victims": "priority_victims",
            "published": "priority_source",
        }
        need(
            projections["first_decode_only"]["reads"]
            == prior["t2"][old_arm[label]]["compulsory_disk_with_restore"],
            "independent one-interval lower bound",
        )
        if all(not loading for _, loading, _ in snapshots):
            need(
                projections["tiles"]["reads"]
                >= projections["external_calls"]["reads"]
                >= projections["first_decode_only"]["reads"],
                "nested drained cuts",
            )
        arms[label] = projections
    return dict(
        status="REPRODUCED_TILE_BOUNDARY_FLOORS",
        evidence="TRACE_DERIVED_CONDITIONAL",
        protocol_sha256=METHOD,
        source_sha256=src.sha(Path(__file__)),
        journal_sha256=bank_api["JOURNAL"],
        selection_sha256=SELECTION,
        prior_sha256=PRIOR,
        final_descriptor_sha256=final_digest,
        snapshots=[dict(ready=len(a), loading=len(b), queued=q) for a, b, q in snapshots],
        arms=arms,
        model_forwards=0,
        weight_reads=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("part", "selection", "new-output-dir"):
        p.add_argument("--" + key, required=True, type=Path)
    args = p.parse_args()
    out = args.new_output_dir
    out.mkdir(mode=0o700)
    try:
        report = score(args.part, args.selection)
    except (OSError, ValueError, KeyError, IndexError, StopIteration) as exc:
        report = dict(
            status="NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            reason=f"{type(exc).__name__}: {exc}",
        )
    tmp = out / "incoming.json"
    src.possible.save(tmp, report)
    tmp.rename(out / "receipt.json")
    print(report["status"])
    return int(report["status"] != "REPRODUCED_TILE_BOUNDARY_FLOORS")


if __name__ == "__main__":
    raise SystemExit(main())
