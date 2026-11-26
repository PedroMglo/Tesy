"""Coupled first-content and native decode bound for a single prepared state."""

import argparse
import importlib.util
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
spec = importlib.util.spec_from_file_location("decode_set_floor", INT / "t1_set_floor/screen.py")
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)
need, src, sha = sf.need, sf.src, sf.sha
METHOD = "63ddd5f0d3f4613327643221d6d2c6bb3cf694099b33532caca86f099919e2a5"
SET = "3402d411f6baf85cfe82067bf106730776939b4822317e11dee40b3a654d0029"
FIRST = 10**10
DECODE = 47 * 10**9  # Numerator at denominator 6.
REGIONS = ("first_only", "both", "decode_only")


def clock(rows, client, summary):
    opens, calls, spans, seen = {}, {}, [], set()
    for r in rows:
        if r.kind == 1:
            need(r.call not in calls, "duplicate enter")
            calls[r.call] = [r.ns, r.a]
        elif r.kind == 2:
            need(len(calls[r.call]) == 2 and r.a == 0, "missing enter")
            calls[r.call].append(r.ns)
        elif r.kind in (9, 23):
            site = (r.call, r.tile, r.layer, r.wave)
            if r.kind == 9:
                need(site not in seen and not opens, "overlapping callbacks")
                opens[site] = r.ns
                seen.add(site)
            else:
                spans.append((r.call, opens.pop(site), r.ns))
    need(not opens and list(calls) == list(range(1, 49)), "46 evaluations after two calls")
    need([c[1] for c in calls.values()] == [5, 148] + [1] * 46, "decode geometry")
    need(
        all(calls[n][0] <= calls[n][2] <= calls[n + 1][0] for n in range(1, 48))
        and {n for n, _, _ in spans} == set(calls)
        and all(calls[n][0] <= t <= e <= calls[n][2] for n, t, e in spans)
        and all(x[2] <= y[1] for x, y in zip(spans, spans[1:], strict=False)),
        "callback not inside synchronous call",
    )
    t = client["timings"]
    usec = Decimal(str(t["predicted_ms"])) * 1000
    need(
        usec == int(usec)
        and summary["decode_s"] == t["predicted_ms"] / 1000
        and summary["prefill_s"] == t["prompt_ms"] / 1000
        and t["predicted_n"] == summary["completion_n"] == summary["predicted_n"] == 47,
        "native clocks/denominator",
    )
    ns = int(usec) * 1000
    interior = calls[48][2] - calls[3][0]
    need(0 < interior <= ns + 1000, "sampler interval does not cover decode calls")
    union = sum(e - t for n, t, e in spans if n >= 3)
    fixed = ns - 1000 - union
    need(fixed >= 0, "negative exterior")
    return calls, dict(
        predicted_ns=ns,
        quantization_concession_ns=1000,
        first_decode_enter_to_last_return_ns=interior,
        decode_callbacks=sum(n >= 3 for n, _, _ in spans),
        decode_remap_union_ns=union,
        fixed_decode_ns=fixed,
        evaluations=46,
        predicted_tokens=47,
    )


def gather(inp, calls, base):
    start = int(inp.client["request_started_monotonic"] * 10**9)
    first = start + int(inp.client["stream_metrics"]["first_final_content_chunk_s"] * 10**9)

    def window(upper):
        plan, _ = src.admit.t2.planner.assemble(inp.rows, inp.meta, start, upper)
        return sf.extract(inp.rows, plan, inp.meta, start, upper)

    # start is always the original POST, including for decode. Never reset first-seen.
    pre, _ = window(calls[2][2] + sf.CALLBACK_MARGIN)
    early, ce = window(first)
    full, ca = window(calls[48][2] + sf.CALLBACK_MARGIN)
    need(
        calls[2][2] < first - sf.CALLBACK_MARGIN
        and pre == early[: len(pre)]
        and early == full[: len(early)]
        and ce == base["conservation"],
        "first-content groups differ",
    )
    return (pre, early[len(pre) :], full[len(early) :]), dict(
        full=ca,
        first_content=ce,
        group_counts=[len(pre), len(early) - len(pre), len(full) - len(early)],
    )


def frontier(regions, eligible, k, a, b, fixed_f, fixed_d):
    """Partition integer places; within each region both objectives order prices identically."""
    keys = [job.key for region in regions for g in region for job in g if job.first]
    need(len(keys) == len(set(keys)), "duplicate first charge across regions")
    tables = [sf.solve(region, eligible, a, b) for region in regions]
    curves = [t[0] for t in tables]
    limits = [len(c) - 1 for c in curves]
    total = min(k, sum(limits))
    den = 4 * b
    best = {}
    temporal_pass = tested = 0
    for q0 in range(min(total, limits[0]) + 1):
        remaining = total - q0
        for q1 in range(max(0, remaining - limits[2]), min(remaining, limits[1]) + 1):
            q2 = remaining - q1
            grant = (q0, q1, q2)
            f = fixed_f * den + curves[0][q0] + curves[1][q1]
            d = fixed_d * den + curves[1][q1] + curves[2][q2]
            tested += 1
            temporal_pass += int(f <= FIRST * den and 6 * d <= DECODE * den)
            score = max(f * DECODE, 6 * d * FIRST)
            for name, order in (
                ("minimum_first", (f, d)),
                ("minimum_decode", (d, f)),
                ("minimum_joint", (score, f, d)),
            ):
                item = (order, grant)
                if name not in best or item < best[name]:
                    best[name] = item

    def choose(name):
        return set().union(*(t[1](q) for t, q in zip(tables, best[name][1], strict=True)))

    return choose, temporal_pass, tested


def report(regions, eligible, volume, selected, k, a, b, fixed_f, fixed_d, budget):
    # If even the whole timing population fits, unused places help the independent volume gate.
    keep = selected | set(
        sorted(eligible - selected, key=lambda key: (key not in volume, key))[: k - len(selected)]
    )
    need(keep <= eligible and len(keep) == k, "selection capacity")
    parts = []
    for reg in regions:
        jobs = [j for g in reg for j in g]
        parts.append(
            dict(
                waves=len(reg),
                jobs=len(jobs),
                selected_first_reads=sum(j.first and j.key in keep for j in jobs),
                first_reads=sum(j.first for j in jobs),
                free_first_read_worker_ns=sum(j.read for j in jobs if j.first and j.key in keep),
                paid_first_read_worker_ns_unscaled=sum(
                    j.read for j in jobs if j.first and j.key not in keep
                ),
                set_worker_ns=sum(j.copies for j in jobs),
                service_num=sum(sf.bounds(g, keep, a, b) for g in reg),
            )
        )
    den = 4 * b
    f = fixed_f * den + parts[0]["service_num"] + parts[1]["service_num"]
    d = fixed_d * den + parts[1]["service_num"] + parts[2]["service_num"]
    vol = len(volume - keep) * src.possible.warm.PAYLOAD
    return dict(
        sha256=src.audit.digest(sorted(keep)),
        selected=len(keep),
        service_den=den,
        regions=dict(zip(REGIONS, parts, strict=True)),
        first_floor_ns=f // den,
        decode_floor_ns=d // den,
        decode_rate_ceiling=47e9 * den / d,
        first_margin_ns=(FIRST * den - f) // den,
        decode_margin_ns=(DECODE * den - 6 * d) // (6 * den),
        first_pass=f <= FIRST * den,
        decode_pass=6 * d <= DECODE * den,
        prefill_volume_bytes=vol,
        prefill_volume_pass={k: vol <= v for k, v in budget.items()},
    )


def run(args):
    baseline = src.pinned(INT / "t1_set_floor/evidence/receipt.json", SET)
    local = src.pinned(args.score_dir / "receipt.json", sf.SCORE)
    prep = src.pinned(args.prepared_dir / "receipt.json", sf.PREP)
    need(
        sha(HERE / "protocol.md") == METHOD
        and sha(INT / "t1_set_floor/screen.py") == baseline["program_sha256"]
        and prep["selection_sha256"] == sha(args.prepared_dir / "selection.json")
        and baseline["historical_local_score_sha256"] == sf.SCORE,
        "frozen prerequisites",
    )
    inp = src.load_inputs(args.part, args.model, args.inventory, args.prepared_dir)
    need(inp.journal == baseline["journal_sha256"] == local["journal_sha256"], "source identity")
    ids = src.module("decode_gate_native_ids", INT / "../../history_lookup/native_ids/verify.py")
    ids.projection(args.part / src.ARM / "raw", 2, ids.GEOMETRY[1])
    try:
        calls, dec = clock(inp.rows, inp.client, inp.summary)
    except (ValueError, IndexError, KeyError, ArithmeticError) as exc:
        return dict(status="INCONCLUSIVE_NATIVE_CLOCK", reason=str(exc))
    regions, conservation = gather(inp, calls, baseline)
    allowed = set(map(tuple, inp.available["evicted_ready"]))
    volume = src.admit.t2.eligible_sets(inp.rows)["victims"]
    need(len(allowed) == 1698 and len(volume) == 852, "eligibility")
    fixed_f, fixed_d = baseline["first_fixed_ns"], dec["fixed_decode_ns"]
    caps = baseline["volume_budget_bytes"]
    k, scenarios = 353, {}
    for a, b in ((1, 1), (4, 5)):
        choose, passing, tested = frontier(regions, allowed, k, a, b, fixed_f, fixed_d)
        gold = next(row for row in baseline["cases"][f"{a}/{b}"] if row["capacity"] == k)
        curve, original = sf.solve(regions[0] + regions[1], allowed, a, b)
        holders = {
            name: choose(name) for name in ("minimum_first", "minimum_decode", "minimum_joint")
        }
        holders["original_first"] = original(min(k, len(curve) - 1))
        arms = {
            name: report(regions, allowed, volume, keys, k, a, b, fixed_f, fixed_d, caps)
            for name, keys in holders.items()
        }
        old = arms["original_first"]
        need(
            old["sha256"] == gold["selected_sha256"]
            and old["first_floor_ns"]
            == arms["minimum_first"]["first_floor_ns"]
            == gold["first_floor_ns"],
            "unchanged first-content optimum",
        )
        joint_time = any(x["first_pass"] and x["decode_pass"] for x in arms.values())
        need(bool(passing) == joint_time, "joint witness consistency")
        witnessed = any(
            x["first_pass"] and x["decode_pass"] and x["prefill_volume_pass"]["47"]
            for x in arms.values()
        )
        decision = (
            "HEADROOM_ONLY"
            if witnessed
            else "INCONCLUSIVE_VOLUME_TRADEOFF"
            if passing
            else "NO_GO_TWO_CLOCKS"
        )
        scenarios[f"{a}/{b}"] = dict(
            decision=decision,
            temporal_passing_allocations=passing,
            allocations=tested,
            witnesses=arms,
        )
    return dict(
        status="PASS_NATIVE_DECODE_GATE",
        captured_session_status="FAIL_PRESERVED",
        scenarios=scenarios,
        clock=dec,
        conservation=conservation,
        first_fixed_ns=fixed_f,
        prefill_volume_budgets=caps,
        eligible=len(allowed),
        capacity=k,
        new_forwards=0,
        journal_sha256=inp.journal,
        first_control_sha256=SET,
        local_sha256=sf.SCORE,
        archive_sha256=src.PART,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("part", "model", "inventory", "prepared-dir", "score-dir", "new-output-dir"):
        p.add_argument("--" + flag, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except (ValueError, IndexError, KeyError, TypeError, OSError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(protocol_sha256=METHOD, program_sha256=sha(Path(__file__)))
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
