"""Price a sealed T1 state using the subsequent T2 in the same process."""

import importlib.util
from pathlib import Path

INT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("local_victim_prices", INT / "t1_victims/screen.py")
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
opportunity = replay.module(INT / "t1_opportunity/screen.py", "local_opportunity")
need = replay.need
CAPACITY = 353
CLOSED = "NO_GO_IN_THIS_OPPORTUNITY"


def opportunities(groups, populations, volume, fixed, budgets):
    need(set(populations) == {"evicted_ready", "all_available"}, "Both T1 regions required")
    pools = {}
    for name, members in populations.items():
        pool = set(map(tuple, members))
        need(
            len(pool) == len(members)
            and all(0 <= layer < 36 and 0 <= expert < 128 for layer, expert in pool),
            "pool integrity",
        )
        pools[name] = pool
    need(pools["evicted_ready"] <= pools["all_available"], "expanded opportunity")
    out = {}
    for name, pool in pools.items():
        caps = list(dict.fromkeys([0, 239, 353, len(pool)]))
        out[name] = dict(
            population=len(pool),
            population_sha256=opportunity.source.digest(sorted(pool)),
            eligible_volume_keys=len(pool & volume),
            rows=opportunity.price(groups, pool, volume, fixed, budgets, caps),
        )
    return out


def dominated(opportunity_report):
    """Only a proof against every allowed victim selection suppresses vote scoring."""
    row = next(r for r in opportunity_report["evicted_ready"]["rows"] if r["capacity"] == CAPACITY)
    return all(row["scales"][scale]["decisions"]["47"] == CLOSED for scale in ("1/1", "4/5"))


def t1_copy_report(rows, family, bank, row):
    keys = [tuple(k) for k in bank["ordered_keys"]]
    need(
        len(keys) == len(set(keys)) == CAPACITY
        and opportunity.source.digest(keys) == bank["ordered_keys_sha256"],
        "full causal bank identity",
    )
    model = replay.Policy(family, CAPACITY, keys)
    actual = replay.simulate(rows, model)
    need(
        actual["decode_hits"] == row["decode_hits"]
        and actual["remaining_prefill_bytes"] == row["remaining_prefill_bytes"],
        "policy agreement",
    )
    costs = {}
    for tier in ("cpu", "cuda"):
        stat = bank["tier"][tier]
        name = "initial_" + tier
        alive = stat["surviving"]
        if family == "victims":
            v = model.victims.stats[name]
            need(v["copies_of_victims"] == alive, "initial victims")
            used = v["reused_installs"]
        else:
            # Each seeded admission distinct from every real generation by slot -1.
            uses = [used for origin, used in model.pub.admissions.values() if origin == name]
            need(len(uses) == alive, "initial published payloads")
            used = sum(uses)
        total = stat["installs"]
        need(
            0 <= used <= alive <= total and total - alive == stat.get("discarded_in_t1", 0),
            "T1/T2 copies",
        )
        costs[tier] = {
            **stat,
            "useful_through_t2": used,
            "unused_through_t2": total - used,
            "unused_bytes": (total - used) * replay.T,
        }
    return costs


def evaluate(inputs):
    current = replay.analyse_arm(
        inputs.rows, inputs.summary, inputs.client, inputs.meta, inputs.prefix, inputs.memory
    )
    need(
        len(current["arms"]) == 8
        and len({(r["family"], r["k"], r["warm"]) for r in current["arms"]}) == 8,
        "independent arms",
    )
    start = int(inputs.client["request_started_monotonic"] * 10**9)
    first = start + int(inputs.client["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    plan, cold = replay.planner.assemble(inputs.rows, inputs.meta, start, first)
    groups = replay.oracle.jobs({"groups": plan}, inputs.rows)
    need(
        sum(map(len, groups)) == current["first_jobs"]
        and cold
        == current["original_service_floor_ns"]
        == sum(replay.mandatory.lower_bound([ns for _, ns in g]) for g in groups),
        "own first jobs/prices",
    )
    volume = replay.eligible_sets(inputs.rows)["victims"]
    prices = opportunities(
        groups, inputs.available, volume, current["fixed_ns"], current["budgets"]
    )
    costs = {
        str(k): {
            name: v
            for name, v in inputs.prefix["capacities"][str(k)].items()
            if name != "ordered_keys"
        }
        for k in (239, CAPACITY)
    }
    result = dict(
        status="PASS_LOCAL_T2_RETENTION_DIAGNOSTIC",
        current=current,
        opportunities=prices,
        t1_recency_costs=costs,
        first_jobs=current["first_jobs"],
        first_groups=len(groups),
        compulsory_prefill_keys=len(volume),
        scope="SAME_PROCESS_T2_ONLY",
        model_forwards=0,
    )
    if dominated(prices):
        result["votes"] = dict(status="NOT_RUN_DOMINATED_ON_BOTH_READ_SCALES")
        return result
    banks = inputs.votes["banks"]
    need(
        banks["recency"]["ordered_keys"] == inputs.prefix["capacities"]["353"]["ordered_keys"],
        "same recency preparation",
    )
    if any(len(b["ordered_keys"]) != CAPACITY for b in banks.values()):
        result["votes"] = dict(status="INCONCLUSIVE_PARTIAL_BANK")
        return result
    paired = {}
    for label, bank in banks.items():
        if label == "recency":
            table = current
        else:
            need(label == "votes", "unregistered selection")
            selection = {
                "capacities": {
                    "239": {"identified": False},
                    "353": {"identified": True, "ordered_keys": bank["ordered_keys"]},
                }
            }
            table = replay.analyse_arm(
                inputs.rows, inputs.summary, inputs.client, inputs.meta, selection, inputs.memory
            )
        values = {}
        for family in ("victims", "publication"):
            row = next(
                r
                for r in table["arms"]
                if r["family"] == family and r["warm"] and r["k"] == CAPACITY
            )
            values[family] = dict(arm=row, t1_copies=t1_copy_report(inputs.rows, family, bank, row))
        paired[label] = dict(selection_sha256=bank["ordered_keys_sha256"], by_t2_policy=values)
    result["votes"] = dict(
        status="PASS_CAUSAL_VOTE_COMPARISON",
        primary_t2_policy="victims",
        votes_by_tier=inputs.votes["votes"],
        distinct_victims=inputs.votes["distinct_victims"],
        arms=paired,
    )
    return result
