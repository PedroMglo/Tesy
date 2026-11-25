"""Trace-derived ceilings for a fixed bank of READY victims from T1."""

import argparse
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
METHOD = "aca8b4d35605388cebc336de93566eb860b6b58f363c5649ae4c09002f896a93"
LOCAL = "eb08c93c08201a8074a996a2f898505a452be38f20c03b345df77f9a7a04638a"
spec = importlib.util.spec_from_file_location("bank_sources", INT / "t1_local/source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
replay = source.module("bank_replay", INT / "t1_victims/screen.py")
opportunity = source.possible
need = source.need


def totals(rows):
    """Count complete generations and the returned syscall bytes on the observed side of the cut."""
    pref_bytes, pre_jobs, decode = Counter(), Counter(), Counter()
    pending, finished = {}, set()
    cut = False
    for r in rows:
        if r.kind == 2 and r.call == 2:
            need(not cut and not pending and r.b == r.c == 0, "prefill cut must be drained")
            cut = True
            continue
        if r.kind not in (13, 15, 17):
            continue
        g = source.fd.identity(r)
        key = (r.layer, r.expert)
        need(r.call > 0 and (r.call > 2) == cut, "generation outside its phase")
        if r.kind == 13:
            need(g not in pending and g not in finished, "duplicate dispatch")
            pending[g] = set()
            (decode if cut else pre_jobs)[key] += 1
        elif r.kind == 15:
            need(
                g in pending
                and r.component in (0, 1, 2)
                and r.component not in pending[g]
                and 0 < r.c <= r.b,
                "invalid returned component",
            )
            pending[g].add(r.component)
            if not cut:
                pref_bytes[key] += r.c
        else:
            need(pending.pop(g, None) == {0, 1, 2}, "publication before three reads")
            finished.add(g)
    need(cut and not pending and len(finished) == pre_jobs.total() + decode.total(), "coverage")
    return pref_bytes, pre_jobs, decode


def top(keys, scores, k):
    return set(sorted(keys, key=lambda key: (-scores.get(key, 0), key))[:k])


def witness(keys, pre_bytes, pre_jobs, decode, groups, fixed):
    def hit_count(counts):
        return sum(counts[key] for key in keys)

    def by_tier(weights):
        return {
            tier: sum(weights(key) for key in keys if (key[0] < 25) == (tier == "cpu"))
            for tier in ("cpu", "cuda")
        }

    p = replay.price(groups, keys, fixed)
    saved = hit_count(pre_bytes)
    return dict(
        keys_sha256=replay.fingerprint(sorted(keys)),
        minimum_t1_offer_copy_bytes=by_tier(lambda _: replay.T),
        minimum_t1_offer_copies=by_tier(lambda _: 1),
        unused_selected_keys=sum(pre_jobs[k] + decode[k] == 0 for k in keys),
        prefill_hits=hit_count(pre_jobs),
        prefill_return_bytes_saved=saved,
        prefill_return_bytes_remaining=pre_bytes.total() - saved,
        decode_hits=hit_count(decode),
        t2_delivery_payload_bytes_by_target=by_tier(lambda k: (pre_jobs[k] + decode[k]) * replay.T),
        t2_repeated_deliveries=sum(max(0, pre_jobs[k] + decode[k] - 1) for k in keys),
        **p,
    )


def classify(gates):
    if not all(any(x[i] for x in gates.values()) for i in range(4)):
        return "NO_GO_FIXED_T1_BANK"
    if any(all(x) for x in gates.values()):
        return "HEADROOM_ONLY_PRICE_COPIES"
    return "INCONCLUSIVE_JOINT_SELECTION"


def screen(groups, eligible, metrics, fixed, budgets, memory, caps):
    pre_bytes, pre_jobs, decode = metrics
    curve, recover = opportunity.frontier(groups, eligible)
    output = []
    for k in caps:
        n = min(k, len(curve) - 1)
        time_keys = recover(n)
        time_keys |= top(eligible - time_keys, pre_bytes, k - n)
        sets = {
            "volume": top(eligible, pre_bytes, k),
            "decode": top(eligible, decode, k),
            "time": time_keys,
        }
        need(all(len(s) == k and s <= eligible for s in sets.values()), "eligible bank")
        rows = {s: witness(keys, *metrics, groups, fixed) for s, keys in sets.items()}
        need(curve[n] == rows["time"]["raw_floor_ns"], "DP witness")
        statuses = {}
        fits = replay.host.additional(k) < memory
        for scale, field in (("1/1", "first_at_1_ns"), ("4/5", "first_at_4_5_ns")):
            statuses[scale] = {}
            for count, maximum in budgets.items():
                gates = {
                    s: (
                        r[field] <= 10**10,
                        r["prefill_return_bytes_remaining"] <= maximum,
                        5 * r["decode_hits"] >= decode.total(),
                        fits,
                    )
                    for s, r in rows.items()
                }
                statuses[scale][count] = {
                    "decision": classify(gates),
                    "witnesses_passed": [s for s, v in gates.items() if all(v)],
                    "failed_necessary": [
                        name
                        for i, name in enumerate(("time", "volume", "hits", "ram"))
                        if not any(x[i] for x in gates.values())
                    ],
                }
        output.append(
            dict(
                k=k,
                additional_bytes=replay.host.additional(k),
                fits_ram=fits,
                witnesses=rows,
                gates=statuses,
            )
        )
    return output


def run(args):
    need(source.sha(HERE / "protocol.md") == METHOD, "protocol identity")
    receipt = source.pinned(args.local_dir / "receipt.json", LOCAL)
    need(
        receipt["status"] == "PASS_SINGLE_SESSION_DIAGNOSTIC"
        and receipt["archive_manifest"] == source.PART
        and receipt["source_sha256"] == source.sha(INT / "t1_local/source.py"),
        "local authority",
    )
    seal = source.pinned(args.prepared_dir / "receipt.json", receipt["prepared_sha256"])
    need(
        seal["status"] == "PASS_PREFIX_ONLY"
        and seal["selection_sha256"] == source.sha(args.prepared_dir / "selection.json"),
        "before-T2 seal",
    )
    inputs = source.load_inputs(args.part, args.model, args.inventory, args.prepared_dir)
    need(receipt["journal_sha256"] == inputs.journal, "local journal")
    base = receipt["results"]["current"]
    allowed = set(map(tuple, inputs.available["evicted_ready"]))
    ref = receipt["results"]["opportunities"]["evicted_ready"]
    need(
        len(allowed) == ref["population"]
        and opportunity.source.digest(sorted(allowed)) == ref["population_sha256"],
        "T1 victims",
    )
    t0 = int(inputs.client["request_started_monotonic"] * 1e9)
    final = t0 + int(inputs.client["stream_metrics"]["first_final_content_chunk_s"] * 1e9)
    plan, cold = replay.planner.assemble(inputs.rows, inputs.meta, t0, final)
    groups = replay.oracle.jobs({"groups": plan}, inputs.rows)
    need(
        cold == base["original_service_floor_ns"] and sum(map(len, groups)) == base["first_jobs"],
        "local first service",
    )
    metrics = totals(inputs.rows)
    pre_bytes, pre_jobs, decode = metrics
    budgets = {str(n): replay.host.budget(inputs.summary, n)[1] for n in (47, 46)}
    need(
        budgets == base["budgets"]
        and inputs.memory == base["remaining_memory_bytes"]
        and all(a["decode_jobs"] == decode.total() for a in base["arms"]),
        "local denominators",
    )
    rows = screen(
        groups,
        allowed,
        metrics,
        base["fixed_ns"],
        budgets,
        inputs.memory,
        (0, 239, 353, len(allowed)),
    )
    for row in rows:
        prior = next(v for v in ref["rows"] if v["capacity"] == row["k"])
        need(
            row["witnesses"]["time"]["raw_floor_ns"] == prior["remaining_service_floor_ns"],
            "temporal optimum reproduction",
        )
    return dict(
        status="PASS_FIXED_BANK_DIAGNOSTIC",
        local_sha256=LOCAL,
        journal_sha256=inputs.journal,
        archive_manifest_sha256=source.PART,
        selection_sha256=seal["selection_sha256"],
        population_sha256=ref["population_sha256"],
        budgets=budgets,
        fixed_ns=base["fixed_ns"],
        groups=len(groups),
        mandatory_jobs=base["first_jobs"],
        available_keys=len(allowed),
        memory_bytes=inputs.memory,
        baseline_return_bytes=pre_bytes.total(),
        prefill_jobs=pre_jobs.total(),
        decode_jobs=decode.total(),
        rows=rows,
        model_forwards=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ("part", "model", "inventory", "prepared-dir", "local-dir", "new-output-dir"):
        parser.add_argument("--" + n, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(args)
    except Exception as err:
        result = {"status": "FAIL_PRESERVED", "error": f"{type(err).__name__}: {err}"}
    result.update(protocol_sha256=METHOD, program_sha256=source.sha(Path(__file__)))
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
