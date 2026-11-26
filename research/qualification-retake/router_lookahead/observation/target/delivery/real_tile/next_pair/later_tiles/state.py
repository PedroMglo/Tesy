"""Recover the two warm CPU primaries from the beginning of the sealed C292 process."""

import argparse
import os
from collections import Counter, defaultdict, deque
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SELECT = run_path(str(HERE / "select_pair.py"))
P, OLD, need, sha, blob = (SELECT[k] for k in ("P", "OLD", "need", "sha", "blob"))
BASE = HERE.parents[6]
POLICY = BASE / "phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/manager.py"
JOB = BASE / "igpu_resident_rank/request_budget/device/pack_native/natural_trace/jobs.py"
PINS = {
    "src/llama-moe-stream.cpp": "044d8879be19e5c22331a29bf7a273307756de10675b1341ee9d7077e2dabc62",
    "src/llama-moe-stream.h": "387c9f6ff17dbf74cf2ff4e280854760a1cfad39cabe0a245312564a7763ced4",
}
POLICY_SHA = "ceaa386d3d5994dd02ebc98d148378405bbf0fa46e98e06fd46a3cd48d44a05f"
SELECT_SHA = "a127f3832e67b41173bd1a75d43a4301c5b757f8ffe33b7b1e0b9885ef56097f"


def compare_decisions(site, observed, predicted, demands, target):
    need(observed == predicted, f"reservation/victim/epoch/reason mismatch at {site}")
    need(demands == target, f"demand binding/order mismatch at {site}")


def recover(rows, selection, policy, job):
    src, dst = selection["source"], selection["destination"]
    marks = {
        selection[key]: key for key in ("tile_enter", "source_boundary", "last_offer", "last_wave")
    }
    m = policy["Manager"](
        [(-1, 0, 0, 0)] * 1440, [[0] * 169 for _ in range(36)], 0, 2304, [set() for _ in range(36)]
    )
    cells, claims, reserved, proof, service = {}, {}, {}, {}, {}
    fifo, seen, refs = deque(), defaultdict(set), {}
    workers, sets, result, history = set(), defaultdict(list), {}, {}
    ncallbacks, nnew = Counter(), Counter()
    previous, current, ranks, fresh, demands = {}, None, {}, [], []
    packfile = None
    pack = {}
    for i, r in enumerate(rows[: max(marks) + 1]):
        k, loc = (r.layer, r.expert, r.slot, r.gen), (r.layer, r.slot)
        if r.kind in (6, 15, 18, 24, 28):
            raise ValueError(
                f"unexpected initial queue, GGUF read, failure, exit or cancellation at {i}"
            )
        if r.kind == 5:
            need(
                loc not in cells and (r.expert, r.gen, r.a, r.b) == (-1, 0, 0, 0), "non-cold entry"
            )
            cells[loc] = (k, 0)
        elif r.kind == 29:
            need(packfile is None and r.fd >= 0 and r.c & os.O_DIRECT, "PACK_FILE")
            packfile = r.fd
            pack = dict(dev=r.a, inode=r.b)
        elif r.kind == 9:
            need(current is None, "nested remap")
            current = r.call, r.tile, r.layer, r.wave
            fresh, demands = [], []
            if r.wave in (0, -1):
                ranks[current[:3]] = []
        elif r.kind == 27:
            need(current is not None and current[3] in (0, -1), "rank origin")
            ranks[current[:3]].extend(P["rank4"](r.a))
        elif r.kind == 11:
            old, code = cells[loc]
            need(
                current == (r.call, r.tile, r.layer, r.wave)
                and code != 1
                and k not in reserved
                and (old[1], old[3]) == (r.a, r.gen - 1),
                "old resident or epoch",
            )
            seen[r.layer].add(r.expert)
            reserved[k] = i
            fresh.append((r.expert, r.slot, r.gen, r.a))
            cells[loc] = k, 1
        elif r.kind == 12:
            need(cells[loc] == (k, 1), "enqueue stale slot")
            fifo.append(k)
            if r.a != 1:
                need(
                    r.a in (0, 2)
                    and fresh[-1][:3] == (r.expert, r.slot, r.gen)
                    and len(fresh[-1]) == 4,
                    "enqueue origin",
                )
                fresh[-1] += (r.a,)
        elif r.kind in (13, 14):
            need(fifo and fifo.popleft() == k, "FIFO order")
            if r.kind == 13:
                need(
                    cells[loc] == (k, 1)
                    and r.worker in range(4)
                    and k not in claims
                    and r.worker not in claims.values(),
                    "claim collision",
                )
                workers.add(r.worker)
                claims[k] = r.worker
                service[k] = job["Service"](False, r.ns)
        elif r.kind in (30, 16):
            need(claims.get(k) == r.worker and packfile is not None, "byte service claim")
            service[k].event(r, packfile)
            if r.kind == 30:
                need(k not in refs and r.c == r.b == P["WINDOW"], "incomplete or repeated read")
                refs[k] = i
            else:
                sets[k].append(i)
        elif r.kind == 17:
            need(claims.pop(k) == r.worker and cells[loc] == (k, 1), "publication")
            service.pop(k).finish(r)
            need(len(sets[k]) == 3 and k in refs, "missing packed READ/three SET")
            proof[k] = dict(
                reserve=reserved[k], read=refs[k], sets=sets.pop(k), publish=i, worker=r.worker
            )
            cells[loc] = k, 2
        elif r.kind == 10:
            need(cells[loc][0] == k, "DEMAND")
            demands.append((r.expert, r.slot, r.gen))
        elif r.kind == 23:
            need(current == (r.call, r.tile, r.layer, r.wave), "REMAP_END")
            route = ranks[current[:3]]
            new, want = m.callback(r.layer, r.wave, route)
            compare_decisions(current, fresh, new, demands, want)
            ncallbacks[r.layer] += 1
            nnew[r.layer] += len(new)
            previous[r.layer] = current
            history[r.layer] = list(want)
            current = None
        if i not in marks:
            continue
        need(current is None and len(cells) == 1440, "cut inside remap or initial state incomplete")
        layers = {}
        for layer in (src, dst):
            pool = m.pools[layer]
            slots = []
            for s, (exp, gen) in enumerate(zip(pool.ids, pool.gen, strict=True)):
                key, code = cells[layer, s]
                need(key == (layer, exp, s, gen), "derived & observed slots at cut")
                slots.append(
                    dict(
                        slot=s,
                        expert=exp,
                        generation=gen,
                        state=code,
                        claim=claims.get(key),
                        slot_last_use=pool.ages[s],
                        origin=proof[key] if code == 2 else None,
                    )
                )
            # previous multiwave callbacks finish at the previous tile on both layers at E35.
            # KEEP and row scratch are overwritten before the next reservation; store their last
            # demand/parking history and the logical plan separately from the actual wave count.
            layers[layer] = dict(
                slots=slots,
                seen=sorted(seen[layer]),
                route_hotness=list(pool.heat),
                use_counter=pool.clock,
                plan_pool=list(pool.parking),
                uniq=list(pool.plan),
                plan_capacity=18,
                plan_n_waves=(len(pool.plan) + 17) // 18,
                plan_next_wave=pool.next_wave,
                last_demand=history.get(layer, []),
                last_site=previous.get(layer),
                checked_remaps=ncallbacks[layer],
                checked_reservations=nnew[layer],
            )
        result[marks[i]] = dict(
            record=i,
            manager_calls=m.calls,
            hot_decay_interval=m.interval,
            fifo=list(fifo),
            claims=sorted([*k, v] for k, v in claims.items()),
            loading=[list(k) for k, code in cells.values() if code == 1],
            productive_workers=sorted(workers),
            pools=layers,
        )
    need(len(result) == 4, "all entry marks")
    return result, pack


def run(a, io):
    for rel, pin in PINS.items():
        io.sealed(a.backend / rel, pin)
    need(
        sha(POLICY.read_bytes()) == POLICY_SHA
        and sha((HERE / "select_pair.py").read_bytes()) == SELECT_SHA,
        "frozen selection and policy",
    )
    selected, rows, sites, _ = SELECT["obtain"](a, io)
    if selected["status"] == "NO_ELIGIBLE_LATER_PAIR":
        return selected
    src, dst, tile = selected["source"], selected["destination"], selected["tile"]
    marks, pack_id = recover(rows, selected, run_path(str(POLICY)), run_path(str(JOB)))
    entry = marks["source_boundary"]
    drained = all(
        not any(marks[point][f] for f in ("fifo", "claims", "loading"))
        and marks[point]["productive_workers"] == list(range(4))
        for point in marks
    )
    restore, active, official, descriptor_keys = {}, {}, {}, {}
    for layer in (src, dst):
        warm = entry["pools"][layer]
        restore[layer] = [r for r in warm["slots"] if r["state"] == 2]
        official[layer] = sites[tile, layer]["reserves"]
        active[layer] = sorted(set(sum(sites[tile, layer]["ranks"], [])))
        descriptor_keys[layer] = (
            restore[layer] + official[layer] + [{"expert": e} for e in active[layer]]
        )
    raw_store = OLD["records"](io, a.manifest_dir, src, descriptor_keys, selected["unused"])
    need(
        pack_id == {f: raw_store["pack_stat"][f] for f in ("dev", "inode")}, "live/archive pack FD"
    )
    for r in raw_store["records"].values():
        layer, e = r["layer"], r["expert"]
        r.pop("authoritative")
        r["official_load"] = e in {j["expert"] for j in official[layer]}
        r["active_rank"] = e in active[layer]
        r["ready_at_entry"] = e in {j["expert"] for j in restore[layer]}
        r["offered"] = layer == dst and e in selected["offers"]
    params = OLD["parameters"](io, a, src)
    io.emit("warm-state.json", blob(marks))
    inputs = io.files.copy()
    plan = dict(
        scope="C292_OFFLINE_RESTORE_PLAN_V1",
        selection=selected,
        parameters=params,
        ready={
            layer: [(s["slot"], s["expert"], s["generation"]) for s in rr]
            for layer, rr in restore.items()
        },
        official_reservations=official,
        active_experts=active,
        store=raw_store,
        source_hashes=PINS,
        policy_sha256=POLICY_SHA,
        files_sha256=inputs,
    )
    io.emit("input-plan.json", blob(plan))
    stages = {
        name: {k: v for k, v in cut.items() if k != "pools"}
        | {
            "pools": {
                layer: dict(
                    ready=sum(s["state"] == 2 for s in p["slots"]),
                    clock=p["use_counter"],
                    seen=len(p["seen"]),
                    nonzero_hotness=sum(bool(h) for h in p["route_hotness"]),
                    checked_remaps=p["checked_remaps"],
                    checked_reservations=p["checked_reservations"],
                )
                for layer, p in cut["pools"].items()
            }
        }
        for name, cut in marks.items()
    }
    total = sum(map(len, restore.values()))
    jobs = sum(map(len, official.values()))
    extra = len(selected["unused"])
    return dict(
        status="WARMSLOT_DECISIONS_REPRODUCED" if drained else "INFLIGHT_RECONSTRUCTION_REQUIRED",
        selection_status=selected["status"],
        protocol_sha256=SELECT["PROTOCOL"],
        authorities=dict(
            part23=P["PART23"],
            part116=P["PART116"],
            c292_family=P["FAMILY"],
            c292_review=P["REVIEW"],
            journal=P["PFJ"],
            derived=P["DERIVED"],
            index=raw_store["index_sha256"],
            pack=raw_store["pack_sha256"],
            c270_index=selected["c270_index_sha256"],
            policy=POLICY_SHA,
        ),
        searched=len(selected["visited"]),
        excluded=selected["excluded"],
        excluded_with_false_offers=sum(
            bool(r["unused"]) for r in selected["visited"] if r["reasons"]
        ),
        source=src,
        destination=dst,
        tile=tile,
        positions=selected["positions"],
        offers=selected["offers"],
        unused=selected["unused"],
        golds=selected["golds"],
        cuts=stages,
        bound_records=total,
        warmed_pack_bytes=total * P["WINDOW"],
        warmed_primary_bytes=total * 3 * P["SLAB"],
        official_loads={layer: len(x) for layer, x in official.items()},
        official_pack_bytes=jobs * P["WINDOW"],
        issued_false_offer_pack_bytes=extra * P["WINDOW"],
        store_keys=len(raw_store["records"]),
        input_files=len(inputs),
        pack_pread_bytes=0,
        gguf_bytes=0,
        source_hashes=PINS,
        program_sha256=sha(Path(__file__).read_bytes()),
        selector_sha256=SELECT_SHA,
        inputs_read=dict(io.returned),
        files_sha256=io.files.copy(),
        direct_native_restoration_tested=False,
        worker_wake_timing_reproducible=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("part23", "part116", "bundle", "manifest-dir", "c7", "backend", "new-output-dir"):
        parser.add_argument("--" + field, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    io = P["Inputs"](a.new_output_dir)
    try:
        receipt = run(a, io)
    except Exception as e:
        receipt = dict(status="FAIL_PRESERVED", reason=str(e), files_sha256=io.files.copy())
    io.emit("receipt.json", blob(receipt))
    print(receipt["status"], receipt.get("reason", ""))
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
