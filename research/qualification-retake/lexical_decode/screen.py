"""Price observed past-token route proposals in the four supplied C294 decodes."""

import argparse
import hashlib
import json
import resource
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path[:0] = [str(UNIT), str(UNIT / "primary_entry_timing")]
from primary_entry_timing import screen as first  # noqa: E402
from warm_route_family.grade import FIXTURE  # noqa: E402

backing = first.backing
warm = first.warm
need = backing.require
PROTOCOL = "7f0bacfd0d76f0a2e7fffe2734207e02f6bb92cc09199fd41bf5d979f5f0ddf9"
COLLECT = "38fb346f9cd12b2dba0f2f6015e6378f94cfef0894d0feef83548b4cf200e7be"
MODES = ("none", "lexical_union", "marginal_matched", "lexical_one", "marginal_one")


class History:
    def __init__(self, layers=36):
        self.specific = [defaultdict(Counter) for _ in range(layers)]
        self.marginal = [Counter() for _ in range(layers)]

    def observed(self, token, layer, ranks):
        self.specific[layer][token].update(ranks)
        self.marginal[layer].update(ranks)

    def proposals(self, token):
        result = {mode: [] for mode in MODES}
        for specific, marginal in zip(self.specific, self.marginal, strict=True):
            counts = specific.get(token, {})
            lex = sorted(counts, key=lambda e: (-counts[e], e))
            marg = sorted(marginal, key=lambda e: (-marginal[e], e))[: len(lex)]
            for mode, items in zip(MODES, ([], lex, marg, lex[:1], marg[:1]), strict=True):
                result[mode].append(tuple(items))
        return result


def forecasts(prompt, continuation, witness):
    table = History()
    decode = defaultdict(list)
    for call, _, layer, pos, ids in witness:
        if call <= 9:
            need(0 <= pos < len(prompt), "future position in history")
            table.observed(prompt[pos], layer, ids)
        else:
            step = call - 10
            need(
                0 <= step < len(continuation)
                and pos == len(prompt) + step
                and len(decode[step]) == layer,
                "decode position or layer",
            )
            decode[step].append(tuple(ids))
    seen = Counter(prompt)
    repeated_prior = 0
    plans = []
    for step, token in enumerate(continuation):
        repeated_prior += int(seen[token] > 0)
        plans.append(table.proposals(token))
        need(len(decode[step]) == 36, "incomplete WRT decode")
        for layer, ids in enumerate(decode[step]):
            table.observed(token, layer, ids)
        seen[token] += 1
    return plans, decode, repeated_prior


def assess(mode, plans, demands, groups, entry, fixed):
    layers = len(entry)
    pool = [set(s) for s in entry]
    # A speculative ingress stays valid until its first consumer, however far in the future.
    waiting = [{} for _ in entry]
    tiers = {tier: Counter() for tier in ("CPU", "CUDA")}
    for s, plan in enumerate(plans):
        picked = plan[mode]
        need(len(picked) == layers == len(demands[s]), "wave geometry")
        for pool_index, (proposals, ids) in enumerate(zip(picked, demands[s], strict=True)):
            layer, work = groups[s * layers + pool_index]
            need(layer == pool_index and set(work) <= set(ids), "READ group identity")
            t = tiers["CPU" if pool_index < 25 else "CUDA"]
            for e in proposals:
                t["proposals"] += 1
                if e not in pool[pool_index]:
                    pool[pool_index].add(e)
                    waiting[pool_index][e] = s
                    t["new_prefetches"] += 1
            missing = set(ids) - pool[pool_index]
            need(missing <= set(work), "demand missing first generation")
            t["uncovered_firsts"] += len(missing)
            t["covered_firsts"] += len(work) - len(missing)
            t["read_floor_us"] += max((work[e] for e in missing), default=0)
            t["blocked_groups"] += int(bool(missing))
            for e in ids:
                if e in waiting[pool_index]:
                    step = waiting[pool_index].pop(e)
                    t["used_same_step" if step == s else "used_later_step"] += 1
            pool[pool_index].update(ids)
    for i, debt in enumerate(waiting):
        tiers["CPU" if i < 25 else "CUDA"]["unused_to_end"] += len(debt)
    keys = (
        "proposals",
        "new_prefetches",
        "uncovered_firsts",
        "covered_firsts",
        "read_floor_us",
        "blocked_groups",
        "used_same_step",
        "used_later_step",
        "unused_to_end",
    )
    rows = {}
    for tier, row in tiers.items():
        t = {k: row[k] for k in keys}
        used = t["used_same_step"] + t["used_later_step"]
        need(
            used == t["covered_firsts"] and t["new_prefetches"] == used + t["unused_to_end"],
            "ingress accounting",
        )
        t["new_prefetch_payload_bytes"] = t["new_prefetches"] * first.EXPERT
        t["new_prefetch_plus_remaining_demand_bytes"] = (
            t["new_prefetches"] + t["uncovered_firsts"]
        ) * first.EXPERT
        rows[tier] = t
    total = {k: sum(t[k] for t in rows.values()) for k in rows["CPU"]}
    scales = {
        label: {
            "read": backing.score(total["read_floor_us"], 0, n, d),
            "with_fixed": backing.score(total["read_floor_us"], fixed, n, d),
        }
        for label, n, d in first.SCALES
    }
    return {"tiers": rows, "total": total, "scales": scales}


def arm(raw, name, off, plans, demands, sealed, controls):
    baseline = backing.arm(
        raw, name, controls[0][name + ".native"], controls[1][name], controls[2][name]
    )
    need(
        baseline == sealed and baseline["original_fixed_us"] == baseline["charged_fixed_us"],
        "primary backing baseline",
    )
    entry, facts = backing.boundary.audit_arm(raw, name)
    native = raw / (name + ".native")
    sha = facts["source_sha256"]
    initial = json.loads(backing.pinned(native / "initial.json", sha["initial.json"]))
    result = json.loads(backing.pinned(native / "result.json", sha["result.json"]))
    need(
        off["P_sha256"] == warm.state(initial)
        and off["F_sha256"] == warm.state(result["final"])
        and off["I_sha256"] == facts["boundary_slot_vector_sha256"] == sealed["anchor_sha256"],
        "P/I/F",
    )
    rows = backing.c295.events(native / "events.tsv", True)
    backing.pinned(native / "events.tsv", sha["events.tsv"])
    groups, _, ranks = first.collect(rows, entry)
    for i, (call, layer, ids) in enumerate(ranks):
        need(
            (call - 1, layer) == divmod(i, 36) and tuple(ids) == demands[call - 1][layer],
            "C294/WRT ordered ranks",
        )
    modes = {m: assess(m, plans, demands, groups, entry, sealed["charged_fixed_us"]) for m in MODES}
    ctrl = modes["none"]
    need(
        ctrl["scales"] == sealed["scale"]
        and ctrl["total"]["uncovered_firsts"] == sealed["total"]["required"]
        and ctrl["total"]["blocked_groups"] == sealed["total"]["required_groups"],
        "unchanged no-preparation",
    )
    for m in MODES:
        t = modes[m]["total"]
        need(
            t["covered_firsts"] + t["uncovered_firsts"] == ctrl["total"]["uncovered_firsts"]
            and t["read_floor_us"] <= ctrl["total"]["read_floor_us"],
            "conservation or worsening free oracle",
        )
    for broad, narrow in (("lexical_union", "lexical_one"), ("marginal_matched", "marginal_one")):
        need(
            modes[broad]["total"]["read_floor_us"] <= modes[narrow]["total"]["read_floor_us"],
            "set inclusion",
        )
    for lex, matched in (("lexical_union", "marginal_matched"), ("lexical_one", "marginal_one")):
        need(
            all(
                modes[lex]["tiers"][k]["proposals"] == modes[matched]["tiers"][k]["proposals"]
                for k in ("CPU", "CUDA")
            ),
            "cardinality control",
        )
    return dict(
        r0_native_us=sealed["native_us"],
        fixed_us=sealed["charged_fixed_us"],
        modes=modes,
        c294_sha256=sha,
        boundary_i_sha256=off["I_sha256"],
        ordered_ranks_sha256=off["decode_sha256"],
    )


def decide(arms):
    def threshold(a, name):
        return a["modes"][name]["scales"]["0.8"]["with_fixed"]["excludes"]

    if any(threshold(a, "lexical_union") for a in arms.values()):
        return "NO_GO_JOINT_FIXED_REMAINDER"

    def smaller(a):
        one = a["modes"]["lexical_one"]["total"]
        other = a["modes"]["marginal_one"]["total"]
        return (
            not threshold(a, "lexical_one")
            and one["read_floor_us"] < other["read_floor_us"]
            and one["new_prefetches"] <= other["new_prefetches"]
        )

    return "GO_PAID_SIMULATION_ONLY" if all(map(smaller, arms.values())) else "INCONCLUSIVE"


def run(a, r):
    require_clean = warm.p.git
    need(
        not require_clean(
            HERE, "-c", "core.preloadIndex=false", "-c", "index.threads=1", "status", "--porcelain"
        ),
        "dirty checkout",
    )
    baseline = json.loads(
        backing.pinned(UNIT / "primary_backing/evidence/receipt.json", first.BOUND)
    )
    backing.pinned(Path(backing.__file__), baseline["source_sha256"])
    backing.pinned(Path(first.__file__), COLLECT)
    backing.pinned(Path(backing.c295.__file__), backing.critical.C295)
    backing.pinned(HERE / "protocol.md", PROTOCOL)
    controls = [json.loads(backing.pinned(UNIT / k, v))["arms"] for k, v in backing.PINS.items()]
    supplied = json.loads(backing.pinned(a.fixture, FIXTURE))
    fam = warm.p.family_inputs(a.family, warm.p.FAMILY_SHA)
    r.update(
        commit=require_clean(HERE, "rev-parse", "HEAD"),
        tree=require_clean(HERE, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=PROTOCOL,
        program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        supplied_sha256=FIXTURE,
        wrt_family_sha256=warm.p.FAMILY_SHA,
        primary_backing_sha256=first.BOUND,
        first_generation_source_sha256=COLLECT,
        inputs="supplied input tokens, one revealed at step entry",
        real_weight_bytes=0,
        model_forwards=0,
        gpu=False,
    )
    for case, prompt_len in backing.PROMPT.items():
        _, off = warm.wrt(a.family, case, fam)
        h = off["native_sha256"]["routed-witness.bin"]
        graphs, witness = warm.p.read(
            backing.pinned(a.family / off["native_dir"] / "routed-witness.bin", h)
        )
        warm.p.check_geometry(graphs, case)
        prompt = supplied[case]["ids"]
        steps = supplied[case]["continuation_ids"]
        need(
            len(prompt) == prompt_len
            and len(steps) == 32
            and all(type(t) is int and 0 <= t < 201088 for t in prompt + steps),
            "wrong C276 token geometry",
        )
        need(len(witness) == 35 * (prompt_len + 32) + 41, "WRT pruned row count")
        plans, demands, repeat = forecasts(prompt, steps, witness)
        r["cases"][case] = dict(
            prefix_inputs=prompt_len - 153,
            increment_inputs=153,
            steps=32,
            steps_with_previous_id=repeat,
            history_rows=35 * prompt_len + 9,
            wrt_sha256=h,
        )
        del witness, graphs
        for rep in (2, 3):
            name = f"c294-{case}-{rep}-on"
            r["arms"][name] = arm(
                a.raw_dir, name, off, plans, demands, baseline["arms"][name], controls
            )
    need(len(r["arms"]) == 4, "incomplete family")
    r.update(status="PASS_LEXICAL_DECODE_SCREEN", decision=decide(r["arms"]))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("fixture", "family", "raw-dir", "new-output-dir"):
        p.add_argument("--" + n, required=True, type=Path)
    a = p.parse_args()
    need(
        not any(
            a.new_output_dir.resolve().is_relative_to(x.resolve())
            for x in (a.family, a.raw_dir, a.fixture.parent)
        ),
        "protect source",
    )
    a.new_output_dir.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED", "decision": "INCONCLUSIVE", "arms": {}, "cases": {}}
    try:
        for key, cap in (
            (resource.RLIMIT_CPU, 120),
            (resource.RLIMIT_AS, 512 << 20),
            (resource.RLIMIT_FSIZE, 4 << 20),
        ):
            soft, hard = resource.getrlimit(key)
            resource.setrlimit(key, (min(x for x in (soft, hard, cap) if x >= 0), hard))
        run(a, r)
    except FileNotFoundError as exc:
        r.update(status="NOT_RUN_RAW_REQUIRED", error=Path(exc.filename).name)
    except (
        KeyError,
        ValueError,
        TypeError,
        OSError,
        MemoryError,
        subprocess.SubprocessError,
    ) as exc:
        r["error"] = str(exc) or type(exc).__name__
    dest = a.new_output_dir / "receipt.json"
    tmp = dest.with_suffix(".pending")
    tmp.write_text(json.dumps(r, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(dest)
    print(r["status"], r["decision"])
    return int(r["status"] != "PASS_LEXICAL_DECODE_SCREEN")


if __name__ == "__main__":
    raise SystemExit(main())
