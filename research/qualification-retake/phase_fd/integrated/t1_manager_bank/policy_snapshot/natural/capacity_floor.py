"""Price the compulsory distinct experts even if an arbitrary T1 bank were chosen by an oracle."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
pair = run_path(str(HERE / "pair.py"))
fd, entry, need, pinned, sha = (pair[k] for k in ("fd", "entry", "need", "pinned", "sha"))
PAYLOAD = 13_219_200
RATE = 4_500_000_000
STOP = 19_968 * 2**20
METHOD = "fde869a7fc1def64e6955cd50ba017a1616be3e3a180abd0c71efbbedf62555f"


def price(required, budget_ns, gap_ns, outputs, peak):
    # A lower bound on reads gives an upper bound on what an arbitrarily good bank could do.
    after = budget_ns - gap_ns
    allowed = after * RATE // (10**9 * PAYLOAD)
    minimum = max(0, required - allowed) if after >= 0 else None
    jobs = max(0, required - 353)
    transfer_ns = jobs * PAYLOAD * 10**9 / RATE
    decode_room_s = outputs / 6 + (after - transfer_ns) / 1e9
    ceiling = (STOP - peak - 1) // PAYLOAD
    return dict(
        max_disk_jobs_after_gaps=allowed if after >= 0 else None,
        at_zero_disk_already_fails=after < 0,
        min_arbitrary_prepared_keys=minimum,
        min_payload_bytes=minimum * PAYLOAD if minimum is not None else None,
        raw_key_ceiling_at_fixed_other_peak=ceiling,
        perfect_353_disk_jobs_floor=jobs,
        perfect_353_max_gap_ns_at_6=budget_ns - transfer_ns,
        perfect_353_spare_s=(after - transfer_ns) / 1e9,
        perfect_353_required_decode_tok_s=outputs / decode_room_s if decode_room_s > 0 else None,
        perfect_353_decision="HEADROOM_ONLY" if allowed >= jobs else "NO_GO_CONDITIONAL",
    )


def ready(rows):
    slots, fifo, _ = entry.audit.state_before(rows)
    need(not fifo and all(state == 2 and not claim for _, _, state, claim in slots), "drained cut")
    keys = {(i // 40, e) for i, (e, _, _, _) in enumerate(slots)}
    need(len(keys) == 1440, "duplicate primary occupants")
    return keys


def arm(root, obs):
    receipt = pinned(root / "receipt.json", obs["receipt_sha256"])
    rows, hdr = fd.read_journal(root / "raw/events.pfj")
    need(hdr["journal_sha256"] == obs["journal_sha256"], "observed PFJ1")
    seal = pinned(root / "before-t2.json", receipt["before_t2_sha256"])
    start = seal["records"]
    need(entry.audit.record_digest(rows[:start]) == seal["sha256"] == obs["seal_sha256"], "T1 seal")
    call = rows[start].call
    indexes = [i for i in range(start, len(rows)) if rows[i].kind == 1][:3]
    need(len(indexes) == 3 and indexes[0] == start, "prefill and decode entry")
    need(
        [(rows[i].call, rows[i].a) for i in indexes] == [(call, 5), (call + 1, 148), (call + 2, 1)],
        "natural calls",
    )
    end = indexes[-1]
    primary, final = ready(rows[:start]), ready(rows[:end])
    demand = {(r.layer, r.expert) for r in rows[start:end] if r.kind == 10}
    reserved = {(r.layer, r.expert) for r in rows[start:end] if r.kind == 11}
    results = {}
    for name, required in (("carry", demand - primary), ("restore", (demand | final) - primary)):
        need(required <= reserved, "compulsory key absent from physical reservations")
        count = len(required)
        results[name] = dict(
            required_distinct=count,
            by_tier=entry.audit.per_tier(required),
            scenarios={
                n: price(
                    count,
                    b,
                    obs["prefill_gaps"]["drained_ns"],
                    int(n),
                    obs["physical_maxima"]["cgroup_peak_bytes"],
                )
                for n, b in obs["deadlines_prefill_ns"].items()
            },
        )
    return dict(
        cases=results,
        on_disk_journal_sha256=hdr["journal_sha256"],
        gap_ns=obs["prefill_gaps"]["drained_ns"],
        prefill_ns_budget=obs["deadlines_prefill_ns"],
        final_only=len(final - primary - demand),
        input_tokens=153,
        slots_per_layer=40,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("family", "pair", "new-output-dir"):
        p.add_argument("--" + arg, required=True, type=Path)
    p.add_argument("--pair-sha256", required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        need(sha(HERE / "capacity-floor.md") == METHOD, "frozen pricing hypotheses")
        report = pinned(a.pair, a.pair_sha256)
        need(report["status"] == "REPRODUCED_SNAPSHOT_CLIENT_PAIR", "unqualified control")
        result = dict(
            status="REPRODUCED_ARBITRARY_T1_BANK_FLOOR",
            method_sha256=METHOD,
            pair_sha256=a.pair_sha256,
            program_sha256=sha(Path(__file__)),
            arms={m: arm(a.family / m, report["arms"][m]) for m in ("OFF", "ON")},
        )
    except (ValueError, KeyError, OSError, IndexError, RuntimeError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    tmp = out / "incoming.json"
    with tmp.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.rename(out / "receipt.json")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
