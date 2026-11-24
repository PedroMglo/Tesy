"""Test a fixed physical-slot bijection on the forced C163 nominal continuation."""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def slot_bijection(base, cand):
    a, b = base["slot_expert"], cand["slot_expert"]
    need(Counter(a) == Counter(b), "different initial working sets")
    empty = iter(s for s, e in enumerate(b) if e < 0)
    p = tuple(next(empty) if e < 0 else b.index(e) for e in a)
    need(sorted(p) == list(range(len(a))), "mapping is not a bijection")
    return p


def victim_order(sl, keep):
    def key(s):
        e = sl["slot_expert"][s]
        return (0, s) if e < 0 else (1, sl["route_hotness"][e], sl["slot_last_use"][s], s)

    return sorted(
        (
            s
            for s, state in enumerate(sl["slot_state"])
            if state != 1 and (not keep or not sl["keep"][s])
        ),
        key=key,
    )


def inspect_layer(a, b, p, gen_delta):
    def mapped(field):
        return all(a[field][s] == b[field][t] for s, t in enumerate(p))

    def sequence(field):
        return [p[s] for s in a[field]] == b[field]

    def same_victims(keep):
        return [p[s] for s in victim_order(a, keep)] == victim_order(b, keep)

    def age_partition(sl, slots):
        # Slot identities in tied groups ordered by ascending reference index.
        grouped = {}
        for i, s in enumerate(slots):
            if sl["slot_expert"][s] >= 0:
                grouped.setdefault(sl["slot_last_use"][s], []).append(i)
        return [grouped[k] for k in sorted(grouped)]

    return {
        "resident_set": set(a["slot_expert"]) == set(b["slot_expert"]),
        "payload_map": mapped("slot_expert"),
        "inverse_map": all(
            (p[x] if x >= 0 else -1) == y
            for x, y in zip(a["expert_slot"], b["expert_slot"], strict=True)
        ),
        "empty_physical_positions": [s for s, e in enumerate(a["slot_expert"]) if e < 0]
        == [s for s, e in enumerate(b["slot_expert"]) if e < 0],
        "ready_state": mapped("slot_state"),
        "claimed": mapped("slot_claimed"),
        "gen_equal": mapped("slot_gen"),
        "gen_up_to_initial_offset": all(
            b["slot_gen"][t] - a["slot_gen"][s] == gen_delta[s] for s, t in enumerate(p)
        ),
        "absolute_last_use": mapped("slot_last_use"),
        "relative_age_values": all(
            a["use_counter"] - a["slot_last_use"][s] == b["use_counter"] - b["slot_last_use"][t]
            for s, t in enumerate(p)
        ),
        "occupied_relative_age_values": all(
            a["use_counter"] - a["slot_last_use"][s] == b["use_counter"] - b["slot_last_use"][t]
            for s, t in enumerate(p)
            if a["slot_expert"][s] >= 0
        ),
        "occupied_relative_order_with_ties": age_partition(a, range(len(p))) == age_partition(b, p),
        "victim_order_current_keep": same_victims(True),
        "victim_order_keep_clear": same_victims(False),
        "keep": mapped("keep"),
        "demand_slots": sequence("demand_slots"),
        "plan_pool": sequence("plan_pool"),
        "pool_used": sequence("pool_used"),
        **{
            k: a[k] == b[k]
            for k in (
                "seen",
                "route_hotness",
                "uniq",
                "touched",
                "expert_wave",
                "n_waves",
                "next_wave",
                "plan_capacity",
                "use_counter",
            )
        },
    }


def by_layer(a, b, p, deltas):
    mismatch = {}
    for layer, (x, y, perm, offset) in enumerate(zip(a, b, p, deltas, strict=True)):
        for k, equal in inspect_layer(x, y, perm, offset).items():
            if not equal:
                mismatch.setdefault(k, []).append(layer)
    return mismatch


def digest(obj):
    return hashlib.sha256(json.dumps(obj, separators=(",", ":")).encode()).hexdigest()


def summary(base, cand):
    divergences = [(i, x, y) for i, (x, y) in enumerate(zip(base, cand, strict=False)) if x != y]
    if not divergences and len(base) != len(cand):
        n = min(len(base), len(cand))
        divergences.append((n, base[n : n + 1], cand[n : n + 1]))
    return {
        "control_count": len(base),
        "candidate_count": len(cand),
        "control_digest": digest(base),
        "candidate_digest": digest(cand),
        "first_difference": divergences[0] if divergences else None,
    }


def qualify(control, target):
    from c152_snapshot_read import VECTORS

    need(
        all(
            sl[k] == final[k]
            for sl, final in zip(control.s["layers"], target["layers"], strict=True)
            for k in (*VECTORS, "n_slots", "use_counter", "n_waves", "next_wave", "plan_capacity")
        ),
        "historical control state did not match",
    )
    need(control.s["n_calls"] == target["n_calls"], "global routing counter")
    need(not target["queue"] and not any(w["phase"] for w in target["owned"]), "nonempty endpoint")
    need(not control.queue and not control.owners, "fixture endpoint not drained")


def arm_report(raw, ledger, arm):
    from c152_snapshot_read import snapshot
    from policy import Fixture
    from study import inputs, sha

    class Recorder(Fixture):
        def __init__(self, *args):
            super().__init__(*args)
            self.actions = []

        def expect(self, kind, **f):
            if self.route["call_id"] >= 11 and kind in ("DEMAND", "RESERVE", "EVICT"):
                incoming = f.get("victim", -1)
                self.actions.append(
                    (
                        self.route["call_id"],
                        self.sl["layer"],
                        kind,
                        f["expert"],
                        incoming,
                        f.get("state", -1),
                        f["slot"],
                        f["generation"],
                    )
                )
            super().expect(kind, **f)

    initial, after_prefill, journal, routes, files = inputs(raw, ledger, arm)
    name = f"{arm}.capture/final.snap"
    final_path = raw / name
    meta = json.loads((ledger / "raw-manifest.json").read_text())["files"][name]
    need(
        final_path.stat().st_size == meta["bytes"] and sha(final_path) == meta["sha256"],
        "final witness",
    )
    final = snapshot(final_path, expected_hashes=initial["hashes"])
    need(
        (final["request"], final["sequence"], final["phase"], final["call_id"]) == (2, 2, 2, 57),
        "final call identity",
    )
    with (raw / f"{arm}.capture/calls.tsv").open() as f:
        plan = list(csv.DictReader(f, delimiter="\t"))
    need(
        [(r["call"], r["phase"], r["first"], r["last"]) for r in plan[10:]]
        == [(str(c), "decode", str(2186 + c), str(2186 + c)) for c in range(11, 58)],
        "continuation plan",
    )
    warm = [r for r in routes if r["call_id"] in (9, 10)]
    continuation = [r for r in routes if r["call_id"] >= 11]
    need(
        [(r["call_id"], r["layer"]) for r in continuation]
        == [(c, layer) for c in range(11, 58) for layer in range(36)]
        and all(r["mode"] == 0 and len(r["ids"]) == 4 for r in continuation),
        "continuation shape",
    )
    history = [
        tuple(
            e[k]
            for k in ("call_id", "layer", "kind", "expert", "victim", "state", "slot", "generation")
        )
        for e in journal
        if 11 <= e["call_id"] <= 57 and e["kind"] in ("DEMAND", "RESERVE", "EVICT")
    ]
    results = {}
    for timing in ("early", "late"):
        a, b = Recorder(initial, timing, False), Recorder(initial, timing, True)
        a.run(warm)
        b.run(warm)
        qualify(a, after_prefill)
        need(not b.queue and not b.owners, "candidate prefill not drained")
        maps = [slot_bijection(x, y) for x, y in zip(a.s["layers"], b.s["layers"], strict=True)]
        offsets = [
            [y["slot_gen"][t] - x["slot_gen"][s] for s, t in enumerate(p)]
            for x, y, p in zip(a.s["layers"], b.s["layers"], maps, strict=True)
        ]
        work_id_at_cut = b.s["next_work_id"] - a.s["next_work_id"]
        before = by_layer(a.s["layers"], b.s["layers"], maps, offsets)
        empty = [sl["slot_expert"].count(-1) for sl in a.s["layers"]]
        a.run(continuation)
        b.run(continuation)
        qualify(a, final)
        need(not b.queue and not b.owners, "candidate continuation not drained")
        need(a.actions == history, "generated control actions differ from frozen nominal journal")
        after = by_layer(a.s["layers"], b.s["layers"], maps, offsets)
        logical_base = [row[:6] for row in a.actions]
        logical_cand = [row[:6] for row in b.actions]
        mapped = []
        for call, layer, kind, e, incoming, state, slot, gen in a.actions:
            t = maps[layer][slot] if slot >= 0 else -1
            g = gen + offsets[layer][slot] if slot >= 0 else gen
            mapped.append((call, layer, kind, e, incoming, state, t, g))
        results[timing] = {
            "prefill_unequal_layers_by_field": before,
            "prefill_permuted_slots": sum(i != j for p in maps for i, j in enumerate(p)),
            "prefill_empty_slots_by_tier": {"CPU": sum(empty[:25]), "CUDA0": sum(empty[25:])},
            "prefill_work_id_offset": work_id_at_cut,
            "logical_trajectory": summary(logical_base, logical_cand),
            "trajectory_under_initial_bijection": summary(mapped, b.actions),
            "final_unequal_layers_by_field": after,
            "final_work_id_offset": b.s["next_work_id"] - a.s["next_work_id"],
            "all_endpoints_idle": True,
            "final_control_matches_historical_layers": True,
            "control_journal_actions_matched": True,
            "decode_counts": dict(Counter(row[2] for row in a.actions)),
            "candidate_decode_counts": dict(Counter(row[2] for row in b.actions)),
        }
    return {
        "input_digests": {k: v["sha256"] for k, v in {**files, name: meta}.items()},
        "schedules": results,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("replay-dir", "policy-dir", "repo", "raw-dir", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir()
    try:
        sys.path[:0] = [str(args.policy_dir), str(args.replay_dir), str(args.repo / "tools")]
        from study import C163, sha

        out = {
            "schema": "c163-continuation-isomorphism-v1",
            "protocol_sha256": sha(Path(__file__).with_name("iso_protocol.md")),
            "tested_source": {
                n: sha(path)
                for n, path in (
                    ("fixture", args.policy_dir / "policy.py"),
                    ("controller", args.replay_dir / "replay.py"),
                    ("loader", args.replay_dir / "study.py"),
                )
            },
        }
        need(
            out["protocol_sha256"]
            == "259c8c5d1f42efffbd6da43115d1c4a504b6defce65cdaa6bf03ab5b299666ad",
            "changed experimental protocol",
        )
        out["arms"] = {
            a: arm_report(args.raw_dir, args.repo / "results" / C163, a)
            for a in ("c163-on-1", "c163-on-2")
        }
        pending = args.new_output_dir / ".pending"
        pending.write_text(json.dumps(out, indent=2) + "\n")
        pending.replace(args.new_output_dir / "receipt.json")
    except Exception as exc:
        (args.new_output_dir / "FAIL.json").write_text(json.dumps({"error": str(exc)}) + "\n")
        raise


if __name__ == "__main__":
    main()
