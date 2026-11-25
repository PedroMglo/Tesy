"""Historical demand and preload cost from a new C294 process, through P and I."""

import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

QUAL = Path(__file__).resolve().parents[1]
ROOT = QUAL.parents[1]
sys.path[:0] = [str(QUAL), str(ROOT / "tools")]
import cache_boundary as boundary  # noqa: E402
from r2_causal_gate import initial_identity  # noqa: E402
from warm_route_reference.verify import PROTOCOL, geometry  # noqa: E402

BYTES = 13_219_200
TIERS = ("CPU",) * 25 + ("CUDA0",) * 11
FIXTURE = "c276-post-c274-r2-causal-qualification-20261005T204839Z/development-inputs.json"
FIXTURE_SHA = "ffcd2da79b579960cf43cfb3f696de6f48d50723cfa77ef36a9d5e7fbd48d14a"
PIN = "237e3b8789650fd68b97641c5b8e259d198ed3b1"
MANAGER_SHA = "270ede951c3911c8acbd878600f7bab3692215b820d5853d67071b790297f9fc"
require = boundary.require


def checked(path, sha):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha, "changed input " + path.name)
    return data


def snapshot_counts(snapshot, expected_calls):
    """Total published loads per layer since native empty initialization.

    C294 llama-moe-stream.cpp:210-212,374-381,393-399,418-432. Generation
    starts at zero. Only a reservation increments it, and sets LOADING.
    LOADING can never be a victim. Only validated completion after all native
    reads and copies changes it to RESIDENT. Failed work latches load_failed.
    The locked snapshot in block_native_run.cpp:117-139 rejects that latch,
    claims, LOADING and pending work. Thus every past generation of a drained,
    successful process made one publication, including generations since evicted.
    """
    pools = boundary.slots(snapshot)
    require(type(snapshot["pending_queue"]) is int, "invalid queue count")
    rows = sorted(snapshot["layers"], key=lambda row: row["layer"])
    totals = []
    for row, pool, tier in zip(rows, pools, TIERS, strict=True):
        require(
            row["native_cache_buffer"] == tier and row["logical_bytes_per_load"] == BYTES,
            "wrong tier or expert size",
        )
        for expert, generation, state, claim in pool:
            require(
                all(type(v) is int for v in (expert, generation, state, claim))
                and ((state == 0 and generation == 0) or (state == 2 and generation > 0)),
                "drained slot incompatible with generation history",
            )
        totals.append(sum(entry[1] for entry in pool))
    calls, misses, preloads = (snapshot[k] for k in ("n_calls", "n_miss", "n_preload"))
    require(all(type(v) is int and v >= 0 for v in (calls, misses, preloads)), "counter domain")
    require(calls == expected_calls, "unexpected routed calls since empty initialization")
    require(sum(totals) == misses + preloads, "all new reservations must be charged once")
    return pools, totals


def per_phase(lines, initial, final):
    """Separate incremental and decode admissions without counting queue promotions.

    Run only after cache_boundary.replay verified all component reads/copies,
    generation and claim transitions, P3 routing and the independent final vector.
    Also reconcile per-epoch new P4 against P10 through the exact I barrier.
    """
    require(next(lines).strip() == boundary.HEADER, "C294 header")
    generations = [[e[1] for e in pool] for pool in initial]
    waiting = {}
    reserved, published = Counter(), Counter()
    at_i = False
    for line in lines:
        kind, _, call, _, layer, expert, slot, gen, _, _, _ = map(int, line.split())
        if (kind, call) == (16, 0):
            require(not at_i and not waiting, "undrained or duplicate I")
            at_i = True
        if kind not in (4, 10):
            continue
        require((call == 0 and not at_i) or (1 <= call <= 32 and at_i), "work outside phase")
        require(0 <= layer < 36 and 0 <= slot < 40 and 0 <= expert < 128, "slot identity")
        key = (layer, slot)
        lease = (call, expert, gen)
        phase_key = ("increment" if call == 0 else "decode", layer)
        if kind == 4:
            if gen == generations[layer][slot]:
                require(waiting.get(key) == lease, "invalid same-generation promotion")
            else:
                require(
                    key not in waiting and gen == generations[layer][slot] + 1, "generation jump"
                )
                waiting[key] = lease
                generations[layer][slot] = gen
                reserved[phase_key] += 1
        else:
            require(waiting.pop(key, None) == lease, "stale/unreserved publication")
            published[phase_key] += 1
    require(at_i and not waiting and published == reserved, "unpublished reservations")
    require(generations == [[e[1] for e in pool] for pool in final], "final generations differ")
    return published


def arm_cost(raw, name, case, fixture):
    residents, audit = boundary.audit_arm(raw, name)
    hashes = audit["source_sha256"]
    arm = raw / (name + ".native")
    result = json.loads(checked(arm / "result.json", hashes["result.json"]))
    geometry(result, case)
    require(
        result["status"] == "COMPLETE_NATIVE_R2_CAUSAL_WORK"
        and result["transport"] == "ORIGINAL"
        and result["official_input_ids"] == fixture["ids"]
        and result["teacher_forced_ids"] == fixture["continuation_ids"],
        "profile or supplied work differs",
    )
    widths = result["external_prefill_calls"]

    def callbacks(plan):
        # Last layer has one output row per external call; others visit each ubatch.
        return 35 * sum((w + 31) // 32 for w in plan) + len(plan)

    p, start_loads = snapshot_counts(result["initial"], callbacks(widths[:-1]))
    final, _ = snapshot_counts(result["final"], callbacks(widths + [1] * 32))
    for key in ("n_miss", "n_preload"):
        require(result["initial"][key] <= result["final"][key], "snapshot counter went backwards")
    journal = io.StringIO(checked(arm / "events.tsv", hashes["events.tsv"]).decode())
    events = per_phase(journal, p, final)
    totals = {}
    for tier in ("CPU", "CUDA0"):
        indices = [layer for layer, where in enumerate(TIERS) if where == tier]
        prefix = sum(start_loads[k] for k in indices)
        increment = sum(events["increment", k] for k in indices)
        totals[tier] = {
            "prefix_loads": prefix,
            "increment_loads": increment,
            "total_loads": prefix + increment,
            "prefix_payload_bytes": prefix * BYTES,
            "increment_payload_bytes": increment * BYTES,
            "total_payload_bytes": (prefix + increment) * BYTES,
        }
    require(
        sum(t["increment_loads"] for t in totals.values())
        == audit["counts"]["prefill_publications"],
        "increment differs from full read/copy replay",
    )
    prefix_state = json.dumps(
        initial_identity(result), sort_keys=True, separators=(",", ":")
    ).encode()
    return residents, {
        "tiers": totals,
        "boundary_slot_vector_sha256": audit["boundary_slot_vector_sha256"],
        "boundary_p_sha256": hashlib.sha256(prefix_state).hexdigest(),
        "prefix_demand_reservations": result["initial"]["n_miss"],
        "prefix_preload_reservations": result["initial"]["n_preload"],
        "source_sha256": hashes,
        "c294_backend_commit": PIN,
        "audited_manager_source_sha256": MANAGER_SHA,
    }


def case_control(results_root, case):
    require(case in ("nominal153", "code153"), "unknown C294 case")
    root = Path(results_root)
    proto = json.loads(checked(boundary.MANIFEST.parent / "protocol.json", PROTOCOL))
    require(proto["backend_commit"] == PIN, "C294 manager pin")
    source_hashes = {Path(k).name: v for k, v in proto["file_sha256"].items()}
    for source in ("block_native_run.cpp", "expert_service_window.cpp"):
        checked(ROOT / "tools" / source, source_hashes[source])
    fixture = json.loads(checked(root / FIXTURE, FIXTURE_SHA))[case]
    arms = {}
    previous = None
    for n in (2, 3):
        name = f"c294-{case}-{n}-on"
        members, arm = arm_cost(root / boundary.CAMPAIGN / "raw", name, case, fixture)
        comparison = (
            members,
            arm["tiers"],
            arm["boundary_p_sha256"],
            arm["boundary_slot_vector_sha256"],
        )
        require(previous in (None, comparison), "repeats differ in P, I or paid publications")
        previous = comparison
        arms[name] = arm
    return arms, members
